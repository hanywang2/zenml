#  Copyright (c) ZenML GmbH 2022. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at:
#
#       https://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
#  or implied. See the License for the specific language governing
#  permissions and limitations under the License.
"""CLI functionality to interact with pipelines."""
import os
from typing import Any, Optional, Union

import click

from zenml.cli import utils as cli_utils
from zenml.cli.cli import TagGroup, cli
from zenml.cli.utils import list_options
from zenml.client import Client
from zenml.console import console
from zenml.enums import CliCategories
from zenml.logger import get_logger
from zenml.models import (
    PipelineBuildFilterModel,
    PipelineFilterModel,
    PipelineRunFilterModel,
)
from zenml.models.pipeline_build_models import PipelineBuildBaseModel
from zenml.models.schedule_model import ScheduleFilterModel
from zenml.pipelines import BasePipeline
from zenml.utils import source_utils, uuid_utils

logger = get_logger(__name__)


@cli.group(cls=TagGroup, tag=CliCategories.MANAGEMENT_TOOLS)
def pipeline() -> None:
    """Interact with pipelines, pipeline runs and schedules."""


@pipeline.command(
    "register",
    help="Register a pipeline instance. The SOURCE argument needs to be an "
    "importable source path resolving to a ZenML pipeline instance, e.g. "
    "`my_module.my_pipeline_instance`.",
)
@click.argument("source")
def register_pipeline(source: str) -> None:
    """Register a pipeline.

    Args:
        source: Importable source resolving to a pipeline instance.
    """
    cli_utils.print_active_config()

    if "." not in source:
        cli_utils.error(
            f"The given source path `{source}` is invalid. Make sure it looks "
            "like `some.module.name_of_pipeline_instance_variable` and "
            "resolves to a pipeline object."
        )

    if not Client().root:
        cli_utils.warning(
            "You're running the `zenml pipeline register` command without a "
            "ZenML repository. Your current working directory will be used "
            "as the source root relative to which the `source` argument is "
            "expected. To silence this warning, run `zenml init` at your "
            "source code root."
        )

    try:
        pipeline_instance = source_utils.load_source_path(source)
    except ModuleNotFoundError as e:
        source_root = source_utils.get_source_root_path()
        cli_utils.error(
            f"Unable to import module `{e.name}`. Make sure the source path is "
            f"relative to your source root `{source_root}`."
        )
    except AttributeError as e:
        cli_utils.error("Unable to load attribute from module: " + str(e))

    if not isinstance(pipeline_instance, BasePipeline):
        cli_utils.error(
            f"The given source path `{source}` does not resolve to a pipeline "
            "object."
        )

    pipeline_instance.register()


@pipeline.command("build", help="Build Docker images for a pipeline.")
@click.argument("pipeline_name_or_id")
@click.option(
    "--version",
    "-v",
    type=str,
    required=False,
    help="Optional version of the pipeline.",
)
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True, dir_okay=False),
    required=False,
    help="Path to configuration file for the build.",
)
@click.option(
    "--stack",
    "-s",
    "stack_name_or_id",
    type=str,
    required=False,
    help="Name or ID of the stack to use for the build.",
)
@click.option(
    "--output",
    "-o",
    "output_path",
    type=click.Path(exists=False, dir_okay=False),
    required=False,
    help="Output path for the build information.",
)
def build_pipeline(
    pipeline_name_or_id: str,
    version: Optional[str] = None,
    config_path: Optional[str] = None,
    stack_name_or_id: Optional[str] = None,
    output_path: Optional[str] = None,
) -> None:
    """Build Docker images for a pipeline.

    Args:
        pipeline_name_or_id: Name or ID of the pipeline.
        version: Version of the pipeline.
        config_path: Path to pipeline configuration file.
        stack_name_or_id: Name or ID of the stack for which the images should
            be built.
        output_path: Optional file path to write the output to.
    """
    cli_utils.print_active_config()

    if not Client().root:
        cli_utils.warning(
            "You're running the `zenml pipeline build` command without a "
            "ZenML repository. Your current working directory will be used "
            "as the source root relative to which the registered step classes "
            "will be resolved. To silence this warning, run `zenml init` at "
            "your source code root."
        )

    pipeline_model = Client().get_pipeline(
        name_id_or_prefix=pipeline_name_or_id, version=version
    )

    with cli_utils.temporary_active_stack(stack_name_or_id=stack_name_or_id):
        pipeline_instance = BasePipeline.from_model(pipeline_model)
        build = pipeline_instance.build(config_path=config_path)

    if build:
        cli_utils.declare(f"Created pipeline build `{build.id}`.")

        if output_path:
            cli_utils.declare(
                f"Writing pipeline build output to `{output_path}`."
            )
            with open(output_path, "w") as f:
                f.write(build.yaml(include={"id", "images", "is_local"}))
    else:
        cli_utils.declare("No docker builds required.")


@pipeline.command("run", help="Run a pipeline.")
@click.argument("pipeline_name_or_id")
@click.option(
    "--version",
    "-v",
    type=str,
    required=False,
    help="Optional version of the pipeline.",
)
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True, dir_okay=False),
    required=False,
    help="Path to configuration file for the run.",
)
@click.option(
    "--stack",
    "-s",
    "stack_name_or_id",
    type=str,
    required=False,
    help="Name or ID of the stack to run on.",
)
@click.option(
    "--build",
    "-b",
    "build_path_or_id",
    type=str,
    required=False,
    help="ID or path of the build to use.",
)
def run_pipeline(
    pipeline_name_or_id: str,
    version: Optional[str] = None,
    config_path: Optional[str] = None,
    stack_name_or_id: Optional[str] = None,
    build_path_or_id: Optional[str] = None,
) -> None:
    """Run a pipeline.

    Args:
        pipeline_name_or_id: Name or ID of the pipeline.
        version: Version of the pipeline.
        config_path: Path to pipeline configuration file.
        stack_name_or_id: Name or ID of the stack on which the pipeline should
            run.
        build_path_or_id: ID of file path of the build to use for the pipeline
            run.
    """
    cli_utils.print_active_config()

    if not Client().root:
        cli_utils.warning(
            "You're running the `zenml pipeline run` command without a "
            "ZenML repository. Your current working directory will be used "
            "as the source root relative to which the registered step classes "
            "will be resolved. To silence this warning, run `zenml init` at "
            "your source code root."
        )

    pipeline_model = Client().get_pipeline(
        name_id_or_prefix=pipeline_name_or_id, version=version
    )

    build: Union[str, "PipelineBuildBaseModel", None] = None
    if build_path_or_id:
        if uuid_utils.is_valid_uuid(build_path_or_id):
            build = build_path_or_id
        elif os.path.exists(build_path_or_id):
            build = PipelineBuildBaseModel.from_yaml(build_path_or_id)
        else:
            cli_utils.error(
                f"The specified build {build_path_or_id} is not a valid UUID "
                "or file path."
            )

    with cli_utils.temporary_active_stack(stack_name_or_id=stack_name_or_id):
        pipeline_instance = BasePipeline.from_model(pipeline_model)
        pipeline_instance.run(config_path=config_path, build=build)


@pipeline.command("list", help="List all registered pipelines.")
@list_options(PipelineFilterModel)
def list_pipelines(**kwargs: Any) -> None:
    """List all registered pipelines.

    Args:
        **kwargs: Keyword arguments to filter pipelines.
    """
    cli_utils.print_active_config()
    client = Client()
    with console.status("Listing pipelines...\n"):

        pipelines = client.list_pipelines(**kwargs)

        if not pipelines.items:
            cli_utils.declare("No pipelines found for this filter.")
            return

        cli_utils.print_pydantic_models(
            pipelines,
            exclude_columns=["id", "created", "updated", "user", "workspace"],
        )


@pipeline.command("delete")
@click.argument("pipeline_name_or_id", type=str, required=True)
@click.option(
    "--version",
    "-v",
    help="Optional pipeline version.",
    type=str,
    required=False,
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Don't ask for confirmation.",
)
def delete_pipeline(
    pipeline_name_or_id: str, version: Optional[str] = None, yes: bool = False
) -> None:
    """Delete a pipeline.

    Args:
        pipeline_name_or_id: The name or ID of the pipeline to delete.
        version: The version of the pipeline to delete.
        yes: If set, don't ask for confirmation.
    """
    cli_utils.print_active_config()

    version_suffix = f" (version {version})" if version else ""

    if not yes:
        confirmation = cli_utils.confirmation(
            f"Are you sure you want to delete pipeline "
            f"`{pipeline_name_or_id}{version_suffix}`? This will change all "
            "existing runs of this pipeline to become unlisted."
        )
        if not confirmation:
            cli_utils.declare("Pipeline deletion canceled.")
            return

    try:
        Client().delete_pipeline(
            name_id_or_prefix=pipeline_name_or_id, version=version
        )
    except KeyError as e:
        cli_utils.error(str(e))
    else:
        cli_utils.declare(
            f"Deleted pipeline `{pipeline_name_or_id}{version_suffix}`."
        )


@pipeline.group()
def schedule() -> None:
    """Commands for pipeline run schedules."""


@schedule.command("list", help="List all pipeline schedules.")
@list_options(ScheduleFilterModel)
def list_schedules(**kwargs: Any) -> None:
    """List all pipeline schedules.

    Args:
        **kwargs: Keyword arguments to filter schedules.
    """
    cli_utils.print_active_config()
    client = Client()

    schedules = client.list_schedules(**kwargs)

    if not schedules:
        cli_utils.declare("No schedules found for this filter.")
        return

    cli_utils.print_pydantic_models(
        schedules,
        exclude_columns=["id", "created", "updated", "user", "workspace"],
    )


@schedule.command("delete", help="Delete a pipeline schedule.")
@click.argument("schedule_name_or_id", type=str, required=True)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Don't ask for confirmation.",
)
def delete_schedule(schedule_name_or_id: str, yes: bool = False) -> None:
    """Delete a pipeline schedule.

    Args:
        schedule_name_or_id: The name or ID of the schedule to delete.
        yes: If set, don't ask for confirmation.
    """
    cli_utils.print_active_config()

    if not yes:
        confirmation = cli_utils.confirmation(
            f"Are you sure you want to delete schedule "
            f"`{schedule_name_or_id}`?"
        )
        if not confirmation:
            cli_utils.declare("Schedule deletion canceled.")
            return

    try:
        Client().delete_schedule(name_id_or_prefix=schedule_name_or_id)
    except KeyError as e:
        cli_utils.error(str(e))
    else:
        cli_utils.declare(f"Deleted schedule '{schedule_name_or_id}'.")


@pipeline.group()
def runs() -> None:
    """Commands for pipeline runs."""


@runs.command("list", help="List all registered pipeline runs.")
@list_options(PipelineRunFilterModel)
def list_pipeline_runs(**kwargs: Any) -> None:
    """List all registered pipeline runs for the filter.

    Args:
        **kwargs: Keyword arguments to filter pipeline runs.
    """
    cli_utils.print_active_config()

    client = Client()
    try:
        with console.status("Listing pipeline runs...\n"):
            pipeline_runs = client.list_runs(**kwargs)
    except KeyError as err:
        cli_utils.error(str(err))
    else:
        if not pipeline_runs.items:
            cli_utils.declare("No pipeline runs found for this filter.")
            return

        cli_utils.print_pipeline_runs_table(pipeline_runs=pipeline_runs.items)
        cli_utils.print_page_info(pipeline_runs)


@runs.command("delete")
@click.argument("run_name_or_id", type=str, required=True)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Don't ask for confirmation.",
)
def delete_pipeline_run(
    run_name_or_id: str,
    yes: bool = False,
) -> None:
    """Delete a pipeline run.

    Args:
        run_name_or_id: The name or ID of the pipeline run to delete.
        yes: If set, don't ask for confirmation.
    """
    cli_utils.print_active_config()

    # Ask for confirmation to delete run.
    if not yes:
        confirmation = cli_utils.confirmation(
            f"Are you sure you want to delete pipeline run `{run_name_or_id}`?"
        )
        if not confirmation:
            cli_utils.declare("Pipeline run deletion canceled.")
            return

    # Delete run.
    try:
        Client().delete_pipeline_run(
            name_id_or_prefix=run_name_or_id,
        )
    except KeyError as e:
        cli_utils.error(str(e))
    else:
        cli_utils.declare(f"Deleted pipeline run '{run_name_or_id}'.")


@pipeline.group()
def builds() -> None:
    """Commands for pipeline builds."""


@builds.command("list", help="List all pipeline builds.")
@list_options(PipelineBuildFilterModel)
def list_pipeline_builds(**kwargs: Any) -> None:
    """List all pipeline builds for the filter.

    Args:
        **kwargs: Keyword arguments to filter pipeline builds.
    """
    cli_utils.print_active_config()

    client = Client()
    try:
        with console.status("Listing pipeline builds...\n"):
            pipeline_builds = client.list_builds(**kwargs)
    except KeyError as err:
        cli_utils.error(str(err))
    else:
        if not pipeline_builds.items:
            cli_utils.declare("No pipeline builds found for this filter.")
            return

        cli_utils.print_pydantic_models(
            pipeline_builds,
            exclude_columns=["created", "updated", "user", "workspace"],
        )


@builds.command("delete")
@click.argument("build_id", type=str, required=True)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Don't ask for confirmation.",
)
def delete_pipeline_build(
    build_id: str,
    yes: bool = False,
) -> None:
    """Delete a pipeline build.

    Args:
        build_id: The ID of the pipeline build to delete.
        yes: If set, don't ask for confirmation.
    """
    cli_utils.print_active_config()

    if not yes:
        confirmation = cli_utils.confirmation(
            f"Are you sure you want to delete pipeline build `{build_id}`?"
        )
        if not confirmation:
            cli_utils.declare("Pipeline build deletion canceled.")
            return

    try:
        Client().delete_build(build_id)
    except KeyError as e:
        cli_utils.error(str(e))
    else:
        cli_utils.declare(f"Deleted pipeline build '{build_id}'.")
