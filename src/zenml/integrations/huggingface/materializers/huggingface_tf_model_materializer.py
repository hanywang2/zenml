#  Copyright (c) ZenML GmbH 2021. All Rights Reserved.
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
"""Implementation of the Huggingface TF model materializer."""

import importlib
import os
from tempfile import TemporaryDirectory
from typing import Dict, Type

from transformers import AutoConfig, TFPreTrainedModel  # type: ignore [import]

from zenml.enums import ArtifactType
from zenml.materializers.base_materializer import BaseMaterializer
from zenml.metadata.metadata_types import MetadataType
from zenml.utils import io_utils

DEFAULT_TF_MODEL_DIR = "hf_tf_model"


class HFTFModelMaterializer(BaseMaterializer):
    """Materializer to read Tensorflow model to and from huggingface pretrained model."""

    ASSOCIATED_TYPES = (TFPreTrainedModel,)
    ASSOCIATED_ARTIFACT_TYPE = ArtifactType.MODEL

    def load(self, data_type: Type[TFPreTrainedModel]) -> TFPreTrainedModel:
        """Reads HFModel.

        Args:
            data_type: The type of the model to read.

        Returns:
            The model read from the specified dir.
        """
        super().load(data_type)

        config = AutoConfig.from_pretrained(
            os.path.join(self.uri, DEFAULT_TF_MODEL_DIR)
        )
        architecture = "TF" + config.architectures[0]
        model_cls = getattr(
            importlib.import_module("transformers"), architecture
        )
        return model_cls.from_pretrained(
            os.path.join(self.uri, DEFAULT_TF_MODEL_DIR)
        )

    def save(self, model: TFPreTrainedModel) -> None:
        """Writes a Model to the specified dir.

        Args:
            model: The TF Model to write.
        """
        super().save(model)
        temp_dir = TemporaryDirectory()
        model.save_pretrained(temp_dir.name)
        io_utils.copy_dir(
            temp_dir.name,
            os.path.join(self.uri, DEFAULT_TF_MODEL_DIR),
        )

    def extract_metadata(
        self, model: TFPreTrainedModel
    ) -> Dict[str, "MetadataType"]:
        """Extract metadata from the given `PreTrainedModel` object.

        Args:
            model: The `PreTrainedModel` object to extract metadata from.

        Returns:
            The extracted metadata as a dictionary.
        """
        super().extract_metadata(model)
        return {
            "num_layers": len(model.layers),
            "num_params": model.num_parameters(only_trainable=False),
            "num_trainable_params": model.num_parameters(only_trainable=True),
        }
