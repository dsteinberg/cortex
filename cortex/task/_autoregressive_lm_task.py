from collections import OrderedDict
from typing import Any, Optional

import numpy as np
import torch
from transformers import BertTokenizer

from cortex.data.data_module import TaskDataModule
from cortex.model.leaf import AutoregressiveLanguageModelLeaf
from cortex.task._abstract_task import BaseTask


class AutoregressiveLanguageModelTask(BaseTask):
    def __init__(
        self,
        data_module: TaskDataModule,
        input_map: dict[str, str],
        leaf_key: str,
        root_key: str,
        tokenizer: BertTokenizer,
        corruption_process: Optional[Any] = None,
        corruption_rate: float = 0.1,
        **kwargs,
    ) -> None:
        """
        Non-autoregressive text denoising task

        Args:
            data_module: The data module for this task
            input_map: Mapping from root keys to data column names
            leaf_key: Key for this leaf in the neural tree
            root_key: Key for the root node in the neural tree
            tokenizer: Tokenizer used for tokenizing sequences
            corruption_process: Optional corruption process to apply to masked targets during training
            corruption_rate: Fixed rate at which to apply corruption to masked targets (default: 0.1)
        """
        super().__init__(
            data_module=data_module,
            input_map=input_map,
            leaf_key=leaf_key,
            corrupt_train_inputs=True,
            corrupt_inference_inputs=True,
        )
        self.vocab_size = len(tokenizer.vocab)
        self.root_key = root_key
        self.corruption_process = corruption_process
        self.corruption_rate = corruption_rate

    def format_inputs(self, batch: OrderedDict, corrupt_frac: Optional[float] = None) -> dict:
        """
        Format input DataFrame for a `NeuralTree` object
        """
        inputs = {}
        for root_key, input_cols in self.input_map.items():
            inputs[root_key] = {
                "seq_array": np.concatenate([np.array(batch[col]).reshape(-1, 1) for col in input_cols], axis=-1),
                "corrupt_frac": corrupt_frac,
            }
        return inputs

    def create_leaf(self, in_dim: int, branch_key: str) -> AutoregressiveLanguageModelLeaf:
        """
        Create the leaf node for this task to be added to a `NeuralTree` object.
        """
        return AutoregressiveLanguageModelLeaf(
            in_dim=in_dim,
            num_classes=self.vocab_size,
            branch_key=branch_key,
            root_key=self.root_key,
            last_layer_bias=True,
            corruption_process=self.corruption_process,
            corruption_rate=self.corruption_rate,
        )

    def compute_eval_metrics(self, ensemble_output, targets, task_key) -> dict:
        logit_key = f"{task_key}_logits"
        target_key = f"{task_key}_targets"
        logits = ensemble_output[logit_key]
        targets = ensemble_output[target_key][0]
        avg_token_probs = logits.softmax(-1).mean(0)
        top_1 = avg_token_probs.argmax(-1)
        task_metrics = {
            "nll": -1.0 * torch.distributions.Categorical(probs=avg_token_probs).log_prob(targets).mean().item(),
            "top_1_acc": top_1.eq(targets).float().mean().item(),
        }
        return task_metrics
