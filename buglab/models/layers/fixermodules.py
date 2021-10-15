from typing import Any, Dict

import torch
import torch.nn as nn
from ptgnn.baseneuralmodel import ModuleWithMetrics


class TextRepairModule(ModuleWithMetrics):
    def __init__(self, input_representation_size: int, rewrite_vocab_size: int):
        super().__init__()
        self.__text_rewrite_embeddings = nn.Embedding(rewrite_vocab_size, embedding_dim=input_representation_size)

    def _reset_module_metrics(self) -> None:
        self.__num_correct = 0
        self.__num_samples = 0

    def _module_metrics(self) -> Dict[str, Any]:
        if self.__num_samples == 0:
            return {}
        return {
            "Text Repair Fixer Accuracy": self.__num_correct / self.__num_samples,
            "Text Repair Fixer Stats": f"{self.__num_correct / self.__num_samples:.2%} ({self.__num_correct}/{self.__num_samples})",
        }

    def compute_rewrite_logits(self, target_rewrite_node_representations, candidate_rewrites):
        """
        :param target_rewrite_node_representations [N, D]
        :param candidate_rewrites: [N]
        """
        embedded_target_rewrites = self.__text_rewrite_embeddings(candidate_rewrites)  # [N, D]
        return torch.einsum("nd,nd->n", embedded_target_rewrites, target_rewrite_node_representations)  # [N]

    def forward(self, rewrite_logprobs, targets, selected_fixes=None):
        """
        :param rewrite_logprobs: [N]
        :param targets: [B]
        :param selected_fixes: Optional [B]
        :return: [B]
        """
        if selected_fixes is not None:
            with torch.no_grad():
                self.__num_correct += int(selected_fixes[targets].sum())
                self.__num_samples += int(targets.shape[0])

        return -rewrite_logprobs[targets]


class SingleCandidateNodeSelectorModule(ModuleWithMetrics):
    # TODO: This could be arbitrarily more complex, instead of computing the inner product of the representations.

    def compute_per_slot_log_probability(self, slot_representations_per_target, target_nodes_representations):
        """
        :param slot_representations_per_target:  [N, D]
        :param target_nodes_representations: [N, D]
        """
        return torch.einsum("nd,nd->n", slot_representations_per_target, target_nodes_representations)  # [N]

    def _reset_module_metrics(self) -> None:
        self.__num_correct = 0
        self.__num_samples = 0

    def _module_metrics(self) -> Dict[str, Any]:
        if self.__num_samples == 0:
            return {}
        return {
            "VarMisuse Repair Fixer Accuracy": self.__num_correct / self.__num_samples,
            "VarMisuse Repair Fixer Stats": f"{self.__num_correct / self.__num_samples:.2%} ({self.__num_correct}/{self.__num_samples})",
        }

    def forward(self, per_slot_logprobs, correct_symbol_node_idxs, selected_fixes=None):
        """

        :param per_slot_logprobs: [N]
        :param correct_symbol_node_idxs: [B]
        :return:
        """
        if selected_fixes is not None:
            with torch.no_grad():
                self.__num_correct += int(selected_fixes[correct_symbol_node_idxs].sum())
                self.__num_samples += int(correct_symbol_node_idxs.shape[0])
        return -per_slot_logprobs[correct_symbol_node_idxs]


class CandidatePairSelectorModule(ModuleWithMetrics):
    def __init__(self, input_node_representation: int, hidden_layer_size: int):
        super().__init__()
        self.__pair_to_slot_scoring_l1 = nn.Linear(
            in_features=3 * input_node_representation, out_features=hidden_layer_size
        )
        self.__pair_to_slot_scoring_lout = nn.Linear(hidden_layer_size, 1, bias=False)

    def compute_per_pair_logits(self, slot_representations_per_pair, pair_representations):
        """
        :param slot_representations_per_pair: [N, D]
        :param pair_representations: [N, 2, D]
        """
        pair_representations_flat = pair_representations.reshape(pair_representations.shape[0], -1)  # [N, 2*D]
        pair_representations_flat = torch.cat(
            (pair_representations_flat, slot_representations_per_pair), dim=-1
        )  # [N, 3*D]

        return self.__pair_to_slot_scoring_lout(
            torch.sigmoid(self.__pair_to_slot_scoring_l1(pair_representations_flat))
        ).squeeze(
            -1
        )  # [N]

    def _reset_module_metrics(self) -> None:
        self.__num_correct = 0
        self.__num_samples = 0

    def _module_metrics(self) -> Dict[str, Any]:
        if self.__num_samples == 0:
            return {}
        return {
            "ArgSwap Repair Fixer Accuracy": self.__num_correct / self.__num_samples,
            "ArgSwap Repair Fixes Stats": f"{self.__num_correct / self.__num_samples:.2%} ({self.__num_correct}/{self.__num_samples})",
        }

    def forward(self, per_slot_logprobs, correct_pair_idx, selected_fixes=None):
        """
        :param per_slot_logprobs: [N]
        :param correct_pair_idx: [B]
        """
        if selected_fixes is not None:
            with torch.no_grad():
                self.__num_correct += int(selected_fixes[correct_pair_idx].sum())
                self.__num_samples += int(correct_pair_idx.shape[0])
        return -per_slot_logprobs[correct_pair_idx]
