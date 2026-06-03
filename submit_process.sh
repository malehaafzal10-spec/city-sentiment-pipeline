#!/bin/bash
#SBATCH --job-name=vllm-llama70b
#SBATCH --output=vllm_output_%j.log
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=80G                 
#SBATCH --partition=l4            
#SBATCH --gres=gpu:l4:4           
#SBATCH --time=04:00:00           

# 1. Navigate to your project folder and activate the virtual environment
echo "Activating virtual environment..."
cd /ceph/home/student.aau.dk/kk36bb/Documents/city-sentiment-pipeline
source .venv/bin/activate

# 2. Start the vLLM server
echo "Starting vLLM server across 4 GPUs..."
python -m vllm.entrypoints.openai.api_server \
    --model casperhansen/llama-3.3-70b-instruct-awq \
    --quantization awq \
    --dtype auto \
    --tensor-parallel-size 4 \
    --gpu-memory-utilization 0.95 \
    --max-model-len 4096 \
    --port 8000 &

# 3. Wait for the server to spin up
echo "Waiting for vLLM server..."
while ! curl -s http://localhost:8000/v1/models > /dev/null; do
    sleep 10
done
echo "Server ready!"

# 4. Run your python processing script
echo "Starting data processing..."
python src/r02_relevant_history.py --date 20260525

# 20260527 done
# 20260526 done