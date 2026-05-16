
python build_raw_dataset.py \  
    --min-depth 4 \                
    --max-depth 4 \               
    --require-cpp \
    --max-problems 250 \
    -o data/depth3_cpp.json


python generate_solutions.py \ 
    -i data/raw_data_depth4.json \
    -o data/depth4_solved.json \  
    -n 5          


python generate_tracebench.py \
  -i data/depth4_solved.json \
  -o data/depth4_tracebench.json \
  -d multi_multi \
  -n 5\
  --validate

python evaluate.py --runner your_module:run_debug_session
optional: --max-turns 5 --blame-k 1 3 5