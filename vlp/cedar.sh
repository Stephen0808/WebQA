#CUDA_VISIBLE_DEVICES=2 python decode_webqa.py --new_segment_ids --batch_size 32 --answer_provided_by "txt" --beam_size 5 --split "ind_test|ood_test" --output_dir tmp/qa_alone_txt_0528data  --num_workers 4 --recover_step 18 &&
#CUDA_VISIBLE_DEVICES=2 python decode_webqa.py --new_segment_ids --batch_size 32 --answer_provided_by "txt" --beam_size 5 --split "ind_test|ood_test" --output_dir tmp/qa_alone_txt_0528data  --num_workers 4 --recover_step 18 --no_txt_fact
CUDA_VISIBLE_DEVICES=2 python run_webqa.py --new_segment_ids --train_batch_size 128 --split "ind_test|ood_test" --answer_provided_by 'img' --task_to_learn 'filter' --num_workers 4 --gradient_accumulation_steps 8 --output_dir tmp/tmp-filter_alone_w_img_20chioces_0527 --recover_step 6 --no_img_meta &&
CUDA_VISIBLE_DEVICES=2 python run_webqa.py --new_segment_ids --train_batch_size 128 --split "ind_test|ood_test" --answer_provided_by 'img' --task_to_learn 'filter' --num_workers 4 --gradient_accumulation_steps 8 --output_dir tmp/tmp-filter_alone_w_img_20chioces_0527 --recover_step 6 --no_img_content &&
CUDA_VISIBLE_DEVICES=2 python run_webqa.py --new_segment_ids --train_batch_size 128 --split "ind_test|ood_test" --answer_provided_by 'img' --task_to_learn 'filter' --num_workers 4 --gradient_accumulation_steps 8 --output_dir tmp/tmp-filter_alone_w_img_20chioces_0527 --recover_step 6 --no_img_meta --no_img_content &&
CUDA_VISIBLE_DEVICES=2 python run_webqa.py --new_segment_ids --train_batch_size 128 --split "ind_test|ood_test" --answer_provided_by 'txt' --task_to_learn 'filter' --num_workers 4 --gradient_accumulation_steps 8 --output_dir tmp/filter_alone_txt_20choices_0528data --recover_step 6 --no_txt_fact