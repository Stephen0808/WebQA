import random
from random import randint, shuffle, choices
from random import random as rand
import pickle
import math
import json
from collections import namedtuple
import torch
import torch.nn as nn
import torch.nn.functional as F

from vlp.loader_utils import get_random_word, batch_list_to_batch_tensors, Pipeline

import os
import imghdr
import numpy as np
import sys


def truncate_tokens_pair(tokens_a, tokens_b, max_len, max_len_a=0, max_len_b=0, trunc_seg=None, always_truncate_tail=False):
    num_truncated_a = [0, 0]
    num_truncated_b = [0, 0]
    while True:
        if len(tokens_a) <= max_len_a and len(tokens_b) <= max_len_b:
            break
        if (max_len_a > 0) and len(tokens_a) > max_len_a:
            trunc_tokens = tokens_a
            num_truncated = num_truncated_a
        elif (max_len_b > 0) and len(tokens_b) > max_len_b:
            trunc_tokens = tokens_b
            num_truncated = num_truncated_b
        elif trunc_seg:
            # truncate the specified segment
            if trunc_seg == 'a':
                trunc_tokens = tokens_a
                num_truncated = num_truncated_a
            else:
                trunc_tokens = tokens_b
                num_truncated = num_truncated_b
        else:
            # truncate the longer segment
            if len(tokens_a) > len(tokens_b):
                trunc_tokens = tokens_a
                num_truncated = num_truncated_a
            else:
                trunc_tokens = tokens_b
                num_truncated = num_truncated_b
        # whether always truncate source sequences
        if (not always_truncate_tail) and (rand() < 0.5):
            del trunc_tokens[0]
            num_truncated[0] += 1
        else:
            trunc_tokens.pop()
            num_truncated[1] += 1
    return num_truncated_a, num_truncated_b

class webqaDataset_filter(torch.utils.data.Dataset):
    """ Load image feature path, q, a """
    def __init__(self, dataset_json_path, split, batch_size, tokenizer, use_num_samples, processor, filter_num_choices=10, device=None):
        super().__init__()
        self.processor = processor
        self.tokenizer = tokenizer
        self.batch_size = batch_size
        self.filter_num_choices = filter_num_choices
        self.instance_list = []
        if device is not None:
            self.device=device
        assert os.path.exists(dataset_json_path), "loader.Dataset: dataset json file doesn't exist! {}".format(dataset_json_path)
        with open(dataset_json_path, "r") as f:
            dataset_J = json.load(f)
        count = 0
        for i in dataset_J:
            datum = dataset_J[i]
            if datum['split'] in split:
                if use_num_samples == -1 or count < use_num_samples:
                    Q = self.tokenizer.tokenize(datum['Q'])
                    A = self.tokenizer.tokenize(datum['A'])
                    gold_facts = []
                    distractor_facts = []
                    for fa in datum['SupportingFacts']:
                        gold_facts.append(self.tokenizer.tokenize(fa['fact']))

                    for fa in datum['DistractorFacts']:
                        distractor_facts.append(self.tokenizer.tokenize(fa['fact']))
                    self.instance_list.append((gold_facts, distractor_facts, [], [], Q, A, True, False)) # do_filter_task, context_is_img
                    
                    count += 1

        print("Load {} instances from {} samples".format(len(self.instance_list), count))

    def __len__(self):
        return len(self.instance_list)

    def __getitem__(self, idx):
        gold_facts, distractor_facts, gold_cxt_list, distractor_cxt_list, Q, A, do_filter_task, context_is_img = self.instance_list[idx]
        
        sample_size = self.filter_num_choices - len(gold_facts)
        if len(distractor_facts) < sample_size: sample_size = len(distractor_facts)
        dis_idx_list = random.sample(range(len(distractor_facts)), sample_size)
        distractor_facts = [distractor_facts[i] for i in dis_idx_list]

        instance = (gold_facts, distractor_facts, gold_cxt_list, distractor_cxt_list, Q, A, do_filter_task, context_is_img)
        instance = self.processor(instance, self.filter_num_choices, self.device)
        # Processor returns:
        # (input_ids, segment_ids, input_mask, masked_ids, masked_pos, masked_weights, 
        #       -1, is_distractor, self.task_idx, img, vis_pe, context_is_img)
        return instance

    def __iter__(self): # iterator to load data
        for __ in range(math.ceil(len(self.instance_list) / float(self.batch_size))):
            batch = []
            for _ in range(self.batch_size):
                idx = randint(0, len(self.instance_list)-1) # allow overlap between batches???
                batch.append(self.__getitem__(idx))
            yield batch_list_to_batch_tensors(batch)

class webqaDataset_qa(torch.utils.data.Dataset):
    """ Load image feature path, q, a """
    def __init__(self, dataset_json_path, split, batch_size, tokenizer, use_num_samples, processor, device=None):
        super().__init__()
        self.processor = processor
        self.tokenizer = tokenizer
        self.batch_size = batch_size
        self.instance_list = []
        if device is not None:
            self.device=device
        assert os.path.exists(dataset_json_path), "loader.Dataset: dataset json file doesn't exist! {}".format(dataset_json_path)
        with open(dataset_json_path, "r") as f:
            dataset_J = json.load(f)
        count = 0
        for i in dataset_J:
            datum = dataset_J[i]
            if datum['split'] in split:
                if use_num_samples == -1 or count < use_num_samples:
                    Q = self.tokenizer.tokenize(datum['Q'])
                    A = self.tokenizer.tokenize(datum['A'])
                    gold_facts = []
                    distractor_facts = []
                    for fa in datum['SupportingFacts']:
                        gold_facts.append(self.tokenizer.tokenize(fa['fact']))

                    self.instance_list.append((gold_facts, [], [], [], Q, A, False, False)) # do_filter_task, context_is_img
                    
                    count += 1

        print("Load {} instances from {} samples".format(len(self.instance_list), count))

    def __len__(self):
        return len(self.instance_list)

    def __getitem__(self, idx):
        instance = self.instance_list[idx]
        instance = self.processor(instance, self.device)
        # Processor returns:
        # (input_ids, segment_ids, input_mask, masked_ids, masked_pos, masked_weights, 
        #       -1, is_distractor, self.task_idx, img, vis_pe, context_is_img)
        return instance

    def __iter__(self): # iterator to load data
        for __ in range(math.ceil(len(self.instance_list) / float(self.batch_size))):
            batch = []
            for _ in range(self.batch_size):
                idx = randint(0, len(self.instance_list)-1) # allow overlap between batches???
                batch.append(self.__getitem__(idx))
            yield batch_list_to_batch_tensors(batch)

class webqaDataset_filter_with_img(torch.utils.data.Dataset):
    """ Load image feature path, q, a """
    def __init__(self, dataset_json_path, img_metadata_path, split, batch_size, tokenizer, gold_feature_folder, distractor_feature_folder, use_num_samples, processor, filter_num_choices=10, device=None):
        super().__init__()
        self.processor = processor
        self.tokenizer = tokenizer
        self.batch_size = batch_size
        self.filter_num_choices = filter_num_choices
        self.instance_list = []
        if device is not None:
            self.device=device
        assert os.path.exists(dataset_json_path), "loader.Dataset: dataset json file doesn't exist!"
        assert os.path.exists(img_metadata_path), "loader.Dataset: img metadata json file doesn't exist!"
        assert os.path.exists(gold_feature_folder), "loader.Dataset: gold feature folder doesn't exist!"
        assert os.path.exists(distractor_feature_folder), "loader.Dataset: distractor feature folder doesn't exist!"
        with open(dataset_json_path, "r") as f:
            dataset_J = json.load(f)
        with open(img_metadata_path, "r") as f:
            img_meta = json.load(f)
        count = 0
        for i in dataset_J:
            datum = dataset_J[i]
            if datum['split'] in split:
                if use_num_samples == -1 or count < use_num_samples:
                    Q = self.tokenizer.tokenize(datum['Q'])
                    A = self.tokenizer.tokenize(datum['A'])
                    gold_feature_paths = []
                    distractor_feature_paths = []
                    gold_cxt_list = []
                    distractor_cxt_list = []
                    for im in datum['GoldIds']:
                        image_feature_path = os.path.join(gold_feature_folder, str(im)+'.pkl')
                        assert os.path.exists(image_feature_path), "loader.Dataset: gold image feature for {} doesn't exist!".format(im)
                        gold_feature_paths.append(image_feature_path)
                        img_meta_key = str(int(im))
                        cxt = img_meta[img_meta_key]["name"] + img_meta[img_meta_key]["description"]
                        cxt = cxt.replace("_", " ").strip()
                        gold_cxt_list.append(cxt)

                    for im in datum['DistractorIds']:
                        image_feature_path = os.path.join(distractor_feature_folder, str(im)+'.pkl')
                        if os.path.exists(image_feature_path):
                            img_meta_key = str(int(im))
                            cxt = img_meta[img_meta_key]["name"] + img_meta[img_meta_key]["description"]
                            cxt = self.tokenizer(cxt.replace("_", " ").strip())
                            distractor_feature_paths.append(image_feature_path)
                            distractor_cxt_list.append(cxt)
                    self.instance_list.append((gold_feature_paths, distractor_feature_paths, gold_cxt_list, distractor_cxt_list, Q, A, True, True)) # do_filter_task, context_is_img
                    
                    count += 1

        print("Load {} instances from {} samples".format(len(self.instance_list), count))

    def __len__(self):
        return len(self.instance_list)

    def __getitem__(self, idx):
        gold_feature_paths, distractor_feature_paths, gold_cxt_list, distractor_cxt_list, Q, A, do_filter_task, context_is_img = self.instance_list[idx]
        assert len(distractor_cxt_list) == len(distractor_feature_paths)
        assert len(gold_cxt_list) == len(gold_feature_paths)
        sample_size = self.filter_num_choices - len(gold_feature_paths)
        if len(distractor_feature_paths) < sample_size: sample_size = len(distractor_feature_paths)
        dis_idx_list = random.sample(range(len(distractor_feature_paths)), sample_size)
        distractor_feature_paths = [distractor_feature_paths[i] for i in dis_idx_list]
        distractor_cxt_list = [distractor_cxt_list[i] for i in dis_idx_list]

        instance = (gold_feature_paths, distractor_feature_paths, gold_cxt_list, distractor_cxt_list, Q, A, do_filter_task, context_is_img)
        instance = self.processor(instance, self.filter_num_choices, self.device)
        # Processor returns:
        # (input_ids, segment_ids, input_mask, masked_ids, masked_pos, masked_weights, 
        #       -1, is_distractor, self.task_idx, img, vis_pe, context_is_img)
        return instance

    def __iter__(self): # iterator to load data
        for __ in range(math.ceil(len(self.instance_list) / float(self.batch_size))):
            batch = []
            for _ in range(self.batch_size):
                idx = randint(0, len(self.instance_list)-1) # allow overlap between batches???
                batch.append(self.__getitem__(idx))
            yield batch_list_to_batch_tensors(batch)

class webqaDataset_qa_with_img(torch.utils.data.Dataset):
    """ Load image feature path, q, a """
    def __init__(self, dataset_json_path, img_metadata_path, split, batch_size, tokenizer, gold_feature_folder, distractor_feature_folder, use_num_samples, processor, device=None):
        super().__init__()
        self.processor = processor
        self.tokenizer = tokenizer
        self.batch_size = batch_size
        self.instance_list = []
        if device is not None:
            self.device=device
        assert os.path.exists(dataset_json_path), "loader.Dataset: dataset json file doesn't exist!"
        assert os.path.exists(img_metadata_path), "loader.Dataset: img metadata json file doesn't exist!"
        assert os.path.exists(gold_feature_folder), "loader.Dataset: gold feature folder doesn't exist!"
        assert os.path.exists(distractor_feature_folder), "loader.Dataset: distractor feature folder doesn't exist!"
        with open(dataset_json_path, "r") as f:
            dataset_J = json.load(f)
        with open(img_metadata_path, "r") as f:
            img_meta = json.load(f)
        count = 0
        for i in dataset_J:
            datum = dataset_J[i]
            if datum['split'] in split:
                if use_num_samples == -1 or count < use_num_samples:
                    Q = self.tokenizer.tokenize(datum['Q'])
                    A = self.tokenizer.tokenize(datum['A'])
                    gold_feature_paths = []
                    gold_cxt_list = []
                    for im in datum['GoldIds']:
                        image_feature_path = os.path.join(gold_feature_folder, str(im)+'.pkl')
                        assert os.path.exists(image_feature_path), "loader.Dataset: gold image feature for {} doesn't exist!".format(im)
                        gold_feature_paths.append(image_feature_path)
                        img_meta_key = str(int(im))
                        cxt = img_meta[img_meta_key]["name"] + img_meta[img_meta_key]["description"]
                        cxt = self.tokenizer(cxt.replace("_", " ").strip())
                        gold_cxt_list.append(cxt)
                    self.instance_list.append((gold_feature_paths, [], gold_cxt_list, [], Q, A, False, True)) # do_filter_task, context_is_img )
                    count += 1

        print("Load {} instances from {} samples".format(len(self.instance_list), count))

    def __len__(self):
        return len(self.instance_list)

    def __getitem__(self, idx):
        instance = self.instance_list[idx]
        instance = self.processor(instance, self.device)
        # Processor returns:
        # (input_ids, segment_ids, input_mask, masked_ids, masked_pos, masked_weights, 
        #       -1, is_distractor, self.task_idx, img, vis_pe, context_is_img)
        return instance

    def __iter__(self): # iterator to load data
        for __ in range(math.ceil(len(self.instance_list) / float(self.batch_size))):
            batch = []
            for _ in range(self.batch_size):
                idx = randint(0, len(self.instance_list)-1) # allow overlap between batches???
                batch.append(self.__getitem__(idx))
            yield batch_list_to_batch_tensors(batch)

class Preprocess4webqa(Pipeline):

    def __init__(self, max_pred, mask_prob, vocab_words, indexer, max_len, len_vis_input, max_len_a, max_len_b, max_len_img_cxt=200, new_segment_ids=True, truncate_config={}, local_rank=-1):
        super().__init__()
        self.task_idx = 3 # use task_idx for s2s in relaxed projection layer
        self.max_pred = max_pred
        self.mask_prob = mask_prob
        self.len_vis_input = len_vis_input
        self.vocab_words = vocab_words
        self.indexer = indexer
        self.max_len_img_cxt = max_len_img_cxt
        self._tril_matrix = torch.tril(torch.ones((max_len, max_len), dtype=torch.long))
        self.always_truncate_tail = truncate_config.get('always_truncate_tail', False)
        self.max_len_b = max_len_b
        self.max_len_a = max_len_a
        self.max_len = max_len
        self.trunc_seg = truncate_config.get('trunc_seg', None)
        self.new_segment_ids = new_segment_ids
        assert max_len_a+max_len_b <= max_len, "loader Processor: max_len_a + max_len_b > max_len"

    def __call__(self, instance, filter_num_choices=None, device=None):
        
        if do_filter_task:
            assert filter_num_choices is not None, "must pass in a valid filter_num_choices when doing filter task"
            if context_is_img:
                gold_feature_paths, distractor_feature_paths, gold_cxt_list, distractor_cxt_list, Q, A, do_filter_task, context_is_img = instance
                num_gold = len(gold_feature_paths)
                filter_num_choices = num_gold + len(distractor_feature_paths)
                perm = np.random.permutation(filter_num_choices)
                all_choices_feature_paths = gold_feature_paths + distractor_feature_paths
                all_choices_cxt_list = gold_cxt_list + distractor_cxt_list
                assert len(all_choices_cxt_list) == filter_num_choices and len(all_choices_feature_paths) == filter_num_choices
                all_choices_feature_paths = [all_choices_feature_paths[p] for p in perm]
                all_choices_cxt_list = [all_choices_cxt_list[p] for p in perm]
                label = [1. if p<num_gold else 0. for p in perm]
                input_ids_list = []
                segment_ids_list = []
                input_mask_list = []
                img_list = []
                vis_pe_list = []
                for i in range(filter_num_choices):
                    cxt = all_choices_cxt_list[i]
                    img_path = all_choices_feature_paths[i]
                    assert os.path.exists(img_path), "loader Processor: .pkl file doesn't exist! {}".format(img_path)
                    tokens_a = ['[UNK]'] * self.max_len_img_cxt # 200
                    tokens_b = Q+A
                    max_len_cxt_meta = self.max_len_a - self.max_len_img_cxt # 200
                    truncate_tokens_pair(cxt, tokens_b, max_len=max_len_cxt_meta + self.max_len_b, max_len_a=max_len_cxt_meta, max_len_b=self.max_len_b, trunc_seg=self.trunc_seg, always_truncate_tail=self.always_truncate_tail)
                    tokens_a += cxt
                    # it seems that there is no need to pad cxt_meta to 200
                    #n_pad = self.max_len_a+1 - len(tokens_a) # +1 for the middle SEP
                    #tokens_a.extend(['[PAD]'] * n_pad)
                    tokens = ['[CLS]'] + tokens_a + ['[SEP]'] + tokens_b + ['[SEP]']
                    
                    if self.new_segment_ids:
                        segment_ids = [4] * (len(tokens_a)+2) + [5] * (len(tokens_b)+1)
                    else:
                        segment_ids = [0] * (len(tokens_a)+2) + [1] * (len(tokens_b)+1)

                    

                    # self-attention mask
                    input_mask = torch.zeros(self.max_len, self.max_len, dtype=torch.long)
                    # everyone can attend to img, cxt_meta and Q. Nobody cares attention to A for filter task
                    img_end_pos = 1+self.len_vis_input
                    input_mask[:, img_end_pos].fill_(1)
                    st, end = 1 + self.max_len_img_cxt, len(tokens_a) + 2 + len(Q)
                    input_mask[:, st:end].fill_(1)
                    #st, end = 2 + self.max_len_a, 2 + self.max_len_a + len(Q)
                    #input_mask[:, st:end].fill_(1)

                    input_ids = self.indexer(tokens)
                    n_pad = self.max_len - len(input_ids)
                    input_ids.extend([0] * n_pad)
                    segment_ids.extend([0] * n_pad)

                    try:
                        with open(img_path, "wb") as f:
                            features = pickle.load(f)
                    except:
                        print("can't load pickle file: ", img_path)
                        raise
                    img = features['fc1_features'].detach().cpu().float()
                    cls_label = features['cls_features'].detach().cpu().float()
                    vis_pe = features['pred_boxes'].detach().cpu()

                    # Lazy normalization of the coordinates
                    w_est = torch.max(vis_pe[:, [0, 2]])*1.+1e-5
                    h_est = torch.max(vis_pe[:, [1, 3]])*1.+1e-5
                    vis_pe[:, [0, 2]] /= w_est
                    vis_pe[:, [1, 3]] /= h_est
                    assert h_est > 0, 'loader Processor: box h_est should greater than 0! {}'.format(h_est)
                    assert w_est > 0, 'loader Processor: box w_est should greater than 0! {}'.format(w_est)
                    rel_area = (vis_pe[:, 3]-vis_pe[:, 1])*(vis_pe[:, 2]-vis_pe[:, 0])
                    rel_area.clamp_(0)

                    vis_pe = torch.cat((vis_pe[:, :4], rel_area.view(-1, 1), features['scores'].detach().cpu().view(-1, 1)), -1)
                    normalized_coord = F.normalize(vis_pe.data[:, :5] - 0.5, dim=-1)
                    vis_pe = torch.cat((F.layer_norm(vis_pe, [6]), F.layer_norm(cls_label, [1601])), dim=-1)

                    assert img.size(0) == vis_pe.size(0), "img features and vis_pe should have the same token length!"
                    vis_pad = torch.zeros((self.max_len_img_cxt - img.size(0), img.size(-1)))
                    img = torch.cat((img, vis_pad), dim=0) 
                    pe_pad = torch.zeros((self.max_len_img_cxt - vis_pe.size(0), vis_pe.size(-1)))
                    vis_pe = torch.cat((vis_pe, pe_pad), dim=0)
                    assert vis_pe.size(0) == self.max_len_img_cxt
                    assert img.size(0) == self.max_len_img_cxt
                    input_ids_list.append(input_ids)
                    segment_ids_list.append(segment_ids)
                    input_mask_list.append(input_mask)
                    img_list.append(img)
                    vis_pe_list.append(vis_pe)
                
                logit_mask = [1.] * len(input_ids_list)
                if len(input_ids_list) < filter_num_choices:
                    num_placeholder = filter_num_choices - len(input_ids_list)
                    input_ids_list.extend([input_ids_list[-1]] * num_placeholder)
                    segment_ids_list.extend([segment_ids_list[-1] * num_placeholder])
                    input_mask_list.extend([input_mask_list[-1]] * num_placeholder)
                    img_list.extend([img_list[-1] * num_placeholder])
                    vis_pe_list.extend([vis_pe_list[-1] * num_placeholder])
                    logit_mask.extend([-float("Inf")] * num_placeholder)
                input_ids = torch.stack(input_ids_list, dim=0)
                segment_ids = torch.stack(segment_ids_list, dim=0)
                input_mask = torch.stack(input_mask_list, dim=0)
                img = torch.stack(img_list, dim=0)
                vis_pe = torch.stack(vis_pe_list, dim=0)
                
                # schema: (input_ids, segment_ids, input_mask, masked_ids, masked_pos, masked_weights, is_next_label, do_filter_task, filter_label, logit_mask, self.task_idx, img, vis_pe, context_is_img)
                return (input_ids, segment_ids, input_mask,       None,       None,       None,       -1,       do_filter_task,       label,       logit_mask, self.task_idx, img, vis_pe, , context_is_img)

            else: # do_filter_task && context_is_text
                gold_facts, distractor_facts, gold_cxt_list, distractor_cxt_list, Q, A, do_filter_task, context_is_img = instance
                num_gold = len(gold_facts)
                filter_num_choices = num_gold + len(distractor_facts)
                perm = np.random.permutation(filter_num_choices)
                all_choices_facts = gold_facts + distractor_facts
                all_choices_facts = [all_choices_facts[p] for p in perm]
                label = [1. if p<num_gold else 0. for p in perm]
                input_ids_list = []
                segment_ids_list = []
                input_mask_list = []
                for i in range(filter_num_choices):
                    tokens_a = all_choices_facts[i]
                    tokens_b = Q+A
                    truncate_tokens_pair(tokens_a, tokens_b, max_len=self.max_len_a+self.max_len_b, max_len_a=self.max_len_a, max_len_b=self.max_len_b, trunc_seg=self.trunc_seg, always_truncate_tail=self.always_truncate_tail)
                    tokens = ['[CLS]'] + tokens_a + ['[SEP]'] + tokens_b + ['[SEP]']

                    if self.new_segment_ids:
                        segment_ids = [4] * (len(tokens_a)+2) + [5] * (len(tokens_b)+1)
                    else:
                        segment_ids = [0] * (len(tokens_a)+2) + [1] * (len(tokens_b)+1)

                    # self-attention mask
                    input_mask = torch.zeros(self.max_len, self.max_len, dtype=torch.long)
                    # everyone can attend to cxt and Q. Nobody cares attention to A for filter task
                    input_mask[:len(tokens_a)+2+len(Q)].fill_(1)

                    input_ids = self.indexer(tokens)
                    n_pad = self.max_len - len(input_ids)
                    input_ids.extend([0] * n_pad)
                    segment_ids.extend([0] * n_pad)

                    input_ids_list.append(input_ids)
                    segment_ids_list.append(segment_ids)
                    input_mask_list.append(input_mask)

                logit_mask = [1.] * len(input_ids_list)
                if len(input_ids_list) < filter_num_choices:
                    num_placeholder = filter_num_choices - len(input_ids_list)
                    input_ids_list.extend([input_ids_list[-1]] * num_placeholder)
                    segment_ids_list.extend([segment_ids_list[-1] * num_placeholder])
                    input_mask_list.extend([input_mask_list[-1]] * num_placeholder)
                    logit_mask.extend([-float("Inf")] * num_placeholder)

                input_ids = torch.stack(input_ids_list, dim=0) # 不确定，stack可能需要在collator里面操作
                segment_ids = torch.stack(segment_ids_list, dim=0)
                input_mask = torch.stack(input_mask_list, dim=0)
                # schema: (input_ids, segment_ids, input_mask, masked_ids, masked_pos, masked_weights, is_next_label, do_filter_task, filter_label, logit_mask, self.task_idx, img, vis_pe, context_is_img)
                return (input_ids, segment_ids, input_mask,       None,        None,        None,         -1,         do_filter_task,        label, logit_mask, self.task_idx, None, None, context_is_img)
                raise NotImplementedError
        
        else:
            if context_is_img:
                gold_feature_paths, distractor_feature_paths, gold_cxt_list, distractor_cxt_list, Q, A, do_filter_task, context_is_img = instance
                tokens_a = ['[UNK]'] * self.max_len_img_cxt
                tokens_b = Q+A
                truncate_tokens_pair((tokens_a, tokens_b, max_len=self.max_len_img_cxt + self.max_len_b, max_len_a=self.max_len_img_cxt, trunc_seg=self.trunc_seg, always_truncate_tail=self.always_truncate_tail))
                tokens = ['[CLS]'] + tokens_a + ['[SEP]'] + tokens_b + ['[SEP]']

                if self.new_segment_ids:
                    segment_ids = [4] * (len(tokens_a)+2) + [5] * (len(tokens_b)+1)
                else:
                    segment_ids = [0] * (len(tokens_a)+2) + [1] * (len(tokens_b)+1)

                effective_len_A = len(A)
                n_pred = min(self.max_pred, max(1, int(round(effective_length * self.mask_prob))))
                cand_pos = []
                for i, tk in enumerate(tokens):
                    # only mask tk in A
                    if (i >= len(tokens_a)+2+len(Q)) and tk!=['CLS']:
                        cand_pos.append(i)
                
                shuffle(cand_pos)
                masked_pos = cand_pos[:n_pred]
                masked_tokens = [tokens[pos] for pos in masked_pos] # gth token in masked_pos
                for pos in masked_pos:
                    if rand() < 0.8:
                        tokens[pos] = '[MASK]'
                    elif rand() < 0.5:
                        tokens[pos] = get_random_word(self.vocab_words)

                masked_weights = [1] * len(masked_tokens)

                input_ids = self.indexer(tokens)
                n_pad = self.max_len - len(input_ids)
                input_ids.extend([0] * n_pad)
                segment_ids.extend([0] * n_pad)

                # self-attention mask
                num_img = len(gold_feature_paths)
                input_mask = torch.zero(self.max_len, self.max_len, dtype=torch.long)

                img_end_pos = 1 + self.len_vis_input*num_img
                input_mask[:, img_end_pos].fill_(1)
                st, end = 1 + self.max_len_img_cxt, 2 + len(tokens_a) + len(Q)
                input_mask[:, st:end].fill_(1)
                # Tokens in A can attend to previous tokens in A
                pred_st, pred_end = 2 + len(tokens_a) + len(Q), len(tokens)
                input_mask[pred_st:pred_end, pred_st:pred_end].copy_(self._tril_matrix[:pred_end-pred_st, :pred_end-pred_st])

                # Zero padding for masked target
                if self.max_pred > n_pred:
                    n_pad = self.max_pred - n_pred
                    masked_ids.extend([0] * n_pad)
                    masked_pos.extend([0] * n_pad)
                    masked_weights.extend([0] * n_pad)

                img_list = []
                vis_pe_list = []
                for img_path in gold_feature_paths:
                    assert os.path.exists(img_path), "loader Processor: .pkl file doesn't exist! {}".format(img_path)
                    try:
                        with open(c, "rb") as f:
                            features = pickle.load(f)
                    except:
                        print(c)
                        raise
                    img = features['fc1_features'].detach().cpu().float()
                    cls_label = features['cls_features'].detach().cpu().float()
                    vis_pe = features['pred_boxes'].detach().cpu()

                    # Lazy normalization of the coordinates
                    w_est = torch.max(vis_pe[:, [0, 2]])*1.+1e-5
                    h_est = torch.max(vis_pe[:, [1, 3]])*1.+1e-5
                    vis_pe[:, [0, 2]] /= w_est
                    vis_pe[:, [1, 3]] /= h_est
                    assert h_est > 0, 'loader Processor: box h_est should greater than 0! {}'.format(h_est)
                    assert w_est > 0, 'loader Processor: box w_est should greater than 0! {}'.format(w_est)
                    rel_area = (vis_pe[:, 3]-vis_pe[:, 1])*(vis_pe[:, 2]-vis_pe[:, 0])
                    rel_area.clamp_(0)

                    vis_pe = torch.cat((vis_pe[:, :4], rel_area.view(-1, 1), features['scores'].detach().cpu().view(-1, 1)), -1)
                    normalized_coord = F.normalize(vis_pe.data[:, :5] - 0.5, dim=-1)
                    vis_pe = torch.cat((F.layer_norm(vis_pe, [6]), F.layer_norm(cls_label, [1601])), dim=-1)

                    img_list.append(img)
                    vis_pe_list.append(vis_pe)

                img = torch.cat(img_list, dim=0)
                vis_pe = torch.cat(vis_pe_list, dim=0)
                assert img.size(0) == vis_pe.size(0), "img features and vis_pe should have the same token length!"
                vis_pad = torch.zeros((self.max_len_a - img.size(0), img.size(-1)))#.to(device)
                img = torch.cat((img, vis_pad), dim=0)
                vis_pad = torch.zeros((self.max_len_a - vis_pe.size(0), vis_pe.size(-1)))#.to(device)
                vis_pe = torch.cat((vis_pe, vis_pad), dim=0)
                assert vis_pe.size(0) == self.max_len_a
                assert img.size(0) == self.max_len_a

                # schema: (input_ids, segment_ids, input_mask, masked_ids, masked_pos, masked_weights, is_next_label, do_filter_task, filter_label, logit_mask, self.task_idx, img, vis_pe, context_is_img)
                return (input_ids, segment_ids, input_mask, masked_ids, masked_pos, masked_weights,      -1,      do_filter_task,        None,        None, self.task_idx, img, vis_pe, context_is_img)
            
            
            else:
                gold_facts, distractor_facts, gold_cxt_list, distractor_cxt_list, Q, A, do_filter_task, context_is_img = instance
                tokens_a = sum(gold_facts, [])
                tokens_b = Q+A
                truncate_tokens_pair(tokens_a, tokens_b, max_len=self.max_len_a+self.max_len_b, max_len_a=self.max_len_a, max_len_b=self.max_len_b, trunc_seg=self.trunc_seg, always_truncate_tail=self.always_truncate_tail)
                tokens = ['[CLS]'] + tokens_a + ['[SEP]'] + tokens_b + ['[SEP]']

                if self.new_segment_ids:
                    segment_ids = [4] * (len(tokens_a)+2) + [5] * (len(tokens_b)+1)
                else:
                    segment_ids = [0] * (len(tokens_a)+2) + [1] * (len(tokens_b)+1)

                effective_len_A = len(A)
                n_pred = min(self.max_pred, max(1, int(round(effective_length * self.mask_prob))))
                cand_pos = []
                for i, tk in enumerate(tokens):
                    # only mask tk in A
                    if (i >= len(tokens_a)+2+len(Q)) and tk!=['CLS']:
                        cand_pos.append(i)
                
                shuffle(cand_pos)
                masked_pos = cand_pos[:n_pred]
                masked_tokens = [tokens[pos] for pos in masked_pos] # gth token in masked_pos
                for pos in masked_pos:
                    if rand() < 0.8:
                        tokens[pos] = '[MASK]'
                    elif rand() < 0.5:
                        tokens[pos] = get_random_word(self.vocab_words)

                masked_weights = [1] * len(masked_tokens)

                input_ids = self.indexer(tokens)
                n_pad = self.max_len - len(input_ids)
                input_ids.extend([0] * n_pad)
                segment_ids.extend([0] * n_pad)

                input_mask = torch.zero(self.max_len, self.max_len, dtype=torch.long)
                input_mask[:, len(tokens_a)+2+len(Q)].fill_(1)
                st, end = 2 + len(tokens_a) + len(Q), len(tokens)
                input_mask[pred_st:pred_end, pred_st:pred_end].copy_(self._tril_matrix[:pred_end-pred_st, :pred_end-pred_st])

                # Zero padding for masked target
                if self.max_pred > n_pred:
                    n_pad = self.max_pred - n_pred
                    masked_ids.extend([0] * n_pad)
                    masked_pos.extend([0] * n_pad)
                    masked_weights.extend([0] * n_pad)
                
                # schema: (input_ids, segment_ids, input_mask, masked_ids, masked_pos, masked_weights, is_next_label, do_filter_task, filter_label, logit_mask, self.task_idx, img, vis_pe, context_is_img)
                return (input_ids, segment_ids, input_mask, masked_ids, masked_pos, masked_weights,       -1,      do_filter_task,      None,      None,       self.task_idx, None, None, context_is_img)
                raise NotImplementedError

        if context_is_img:
            tokens_a = ['[UNK]'] * (self.len_vis_input*len(context))
        else:
            tokens_a = context

        # truncate_tokens_pair(tokens_a, tokens_b, max_len, max_len_a=0, max_len_b=0, trunc_seg=None, always_truncate_tail=False):
        tokens_b = Q+A
        truncate_tokens_pair(tokens_a, tokens_b, max_len=self.max_len_a + self.max_len_b, max_len_a=self.max_len_a, max_len_b=self.max_len_b, trunc_seg=self.trunc_seg, always_truncate_tail=self.always_truncate_tail)
        effective_len_a = len(tokens_a)
        # pad tokens_a to max_len_a
        n_pad = self.max_len_a - len(tokens_a)
        tokens_a.extend(['[PAD]'] * n_pad)

        tokens = ['[CLS]'] + tokens_a + ['[SEP]'] + tokens_b + ['[SEP]']
        
        if self.new_segment_ids:
            segment_ids = [4] * (len(tokens_a)+2) + [5] * (len(tokens_b)+1)
        else:
            segment_ids = [0] * (len(tokens_a)+2) + [1] * (len(tokens_b)+1)

        effective_length = len(A)
        n_pred = min(self.max_pred, max(1, int(round(effective_length * self.mask_prob))))
        cand_pos = []
        for i, tk in enumerate(tokens):
            # only mask tk in A
            if (i >= len(tokens_a)+2+len(Q)) and (tk != '[CLS]'): 
                # 有点问题因为算n_pred时effective_length没有加上末尾的[SEP] 
                # 而且 tk != '[CLS]' 也很匪夷所思
                cand_pos.append(i)
        shuffle(cand_pos)
        masked_pos = cand_pos[:n_pred]
        masked_tokens = [tokens[pos] for pos in masked_pos]
        for pos in masked_pos:
            if rand() < 0.8:
                tokens[pos] = '[MASK]'
            elif rand() < 0.5:
                tokens[pos] = get_random_word(self.vocab_words)
        
        # when n_pred < max_pred, we only calculate loss within n_pred
        masked_weights = [1]*len(masked_tokens) # will be pad to length=max_pred later

        # Token Indexing
        try:
            input_ids = self.indexer(tokens)
        except:
            print("\ntokens = ", tokens)
            print("\ntokens_b = ", tokens_b)
            raise
        masked_ids = self.indexer(masked_tokens)

        # Zero Padding
        n_pad = self.max_len - len(input_ids)
        input_ids.extend([0] * n_pad)
        segment_ids.extend([0] * n_pad)

        # self-attention mask
        input_mask = torch.zeros(self.max_len, self.max_len, dtype=torch.long)
        pred_st, pred_end = len(tokens_a)+2 + len(Q), len(tokens)

        # Everybody can attend to context
        input_mask[:, :effective_len_a].fill_(1)
        # Everybody can attend to Q
        input_mask[:, len(tokens_a)+1:len(tokens_a)+1 + len(Q)].fill_(1)
        # Tokens in A can attend to previous tokens in A
        input_mask[pred_st:pred_end, pred_st:pred_end].copy_(\
            self._tril_matrix[:pred_end-pred_st, :pred_end-pred_st])
        
        # Zero Padding for masked target
        if self.max_pred > n_pred:
            n_pad = self.max_pred - n_pred
            masked_ids.extend([0] * n_pad)
            masked_pos.extend([0] * n_pad)
            masked_weights.extend([0] * n_pad)

        if context_is_img:
            # Load img features
            img_list = []
            vis_pe_list = []
            for c in context:
                assert os.path.exists(c), "loader Processor: .pkl file doesn't exist! {}".format(context)
                try:
                    with open(c, "rb") as f:
                        features = pickle.load(f)
                except:
                    print(c)
                    raise
                img = features['fc1_features'].detach().cpu().float()
                cls_label = features['cls_features'].detach().cpu().float()
                vis_pe = features['pred_boxes'].detach().cpu()

                # Lazy normalization of the coordinates
                w_est = torch.max(vis_pe[:, [0, 2]])*1.+1e-5
                h_est = torch.max(vis_pe[:, [1, 3]])*1.+1e-5
                vis_pe[:, [0, 2]] /= w_est
                vis_pe[:, [1, 3]] /= h_est
                assert h_est > 0, 'loader Processor: box h_est should greater than 0! {}'.format(h_est)
                assert w_est > 0, 'loader Processor: box w_est should greater than 0! {}'.format(w_est)
                rel_area = (vis_pe[:, 3]-vis_pe[:, 1])*(vis_pe[:, 2]-vis_pe[:, 0])
                rel_area.clamp_(0)

                vis_pe = torch.cat((vis_pe[:, :4], rel_area.view(-1, 1), features['scores'].detach().cpu().view(-1, 1)), -1)
                normalized_coord = F.normalize(vis_pe.data[:, :5] - 0.5, dim=-1)
                vis_pe = torch.cat((F.layer_norm(vis_pe, [6]), F.layer_norm(cls_label, [1601])), dim=-1)

                img_list.append(img)
                vis_pe_list.append(vis_pe)
            img = torch.cat(img_list, dim=0)
            vis_pe = torch.cat(vis_pe_list, dim=0)
            assert img.size(0) == vis_pe.size(0), "img features and vis_pe should have the same token length!"
            vis_pad = torch.zeros((self.max_len_a - img.size(0), img.size(-1)))#.to(device)
            img = torch.cat((img, vis_pad), dim=0)
            vis_pad = torch.zeros((self.max_len_a - vis_pe.size(0), vis_pe.size(-1)))#.to(device)
            vis_pe = torch.cat((vis_pe, vis_pad), dim=0)
            assert vis_pe.size(0) == self.max_len_a
            assert img.size(0) == self.max_len_a
        return (input_ids, segment_ids, input_mask, masked_ids, masked_pos, masked_weights, -1, do_filter_task, is_distractor, self.task_idx, img, vis_pe, context_is_img)


        







