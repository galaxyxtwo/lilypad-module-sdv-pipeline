#/usr/bin/env python3
import sys
import subprocess
import os
import requests
import json
import threading
import signal
from urllib import request, parse
import time
import subprocess
import logging

def run_comfyui():
    global comfyui_thread
    comfyui_thread = subprocess.Popen(["python3", "/app/ComfyUI/main.py", "--listen", "127.0.0.1", "--output-directory", "/outputs/"])

def stop_comfyui():
    global comfyui_thread
    if comfyui_thread:
        # Send SIGINT (CTRL+C) to the subprocess
        comfyui_thread.send_signal(signal.SIGINT)
        # Wait for the subprocess to terminate
        comfyui_thread.wait()
        # End the thread
        comfyui_thread = None

# Core settings
KSAMPLER_NAMES = ["euler", "euler_ancestral", "heun", "heunpp2","dpm_2", "dpm_2_ancestral",
                  "lms", "dpm_fast", "dpm_adaptive", "dpmpp_2s_ancestral", "dpmpp_sde", "dpmpp_sde_gpu",
                  "dpmpp_2m", "dpmpp_2m_sde", "dpmpp_2m_sde_gpu", "dpmpp_3m_sde", "dpmpp_3m_sde_gpu", "ddpm", "lcm"]
SCHEDULER_NAMES = ["normal", "karras", "exponential", "sgm_uniform", "simple", "ddim_uniform"]

timeout = 30 # If ComfyUI doesn't start within this many seconds, we'll give up
default_steps = 75 # Default number of steps for image generation
video_default_steps = 20 # Default number of steps for video generation
batching = 1 # Default batch size

# Run ComfyUI in a subprocess.
debug_mode = False

# Check if --debug flag is passed
if "--debug" in sys.argv:
    debug_mode = True

# Check if DEBUG_MODE environment variable is set to true
if os.environ.get("DEBUG_MODE") == "true":
    debug_mode = True

# Start ComfyUI in a background thread
comfyui_thread = threading.Thread(target=run_comfyui)
comfyui_thread.start()

# Wait for the server to be ready
startup_check_url = "http://127.0.0.1:8188/queue"
response = None

start_time = time.time()
timer = start_time
delay = 1 # How long to wait between checks

while timer - start_time < timeout:
    try:
        response = requests.get(startup_check_url, timeout=5)
        if response is None or response.status_code != 200:
            if response:
                print(f"Server not ready yet ({response.status_code}). Waiting 1 second...")
            else:
                print("Server not ready yet (no response). Waiting 1 second...")
            time.sleep(delay)
            timer = time.time()
        else:
            break
    except requests.exceptions.RequestException as e:
        print("Server not ready yet (requests raised an exception). Waiting 1 second...")
        time.sleep(delay)
        timer = time.time()

if response is None or response.status_code != 200:
    # Print last status code if available
    if response:
        print(f"Fatal error: Failed to connect to the server. Status code: {response.status_code}")
    print("Fatal error: Failed to connect to the server within the timeout period.")
    sys.exit(1)

# Sleep for a second to give the server time to start up
time.sleep(1)

# Process and submit our job
# ======================================================================
# This function sends a prompt workflow to the specified URL
# (http://127.0.0.1:8188/prompt) and queues it on the ComfyUI server
# running at that address.
def queue_prompt(prompt_workflow):
    p = {"prompt": prompt_workflow}
    data = json.dumps(p).encode('utf-8')
    req =  request.Request("http://127.0.0.1:8188/prompt", data=data)
    request.urlopen(req)
# ======================================================================

# read workflow api data from file and convert it into dictionary
# assign to var prompt_workflow
prompt_workflow = json.load(open('workflow.json'))

# Get prompt from $PROMPT, falling back to "question mark floating in space" if not set
prompt = os.environ.get("PROMPT") or "question mark floating in space"

# Get seed from $SEED, falling back to 42 if not set
seed = os.environ.get("SEED") or "42"

# Get seed from $VIDEOSEED, falling back to 42 if not set
videoseed = os.environ.get("VIDEOSEED") or "42"

# Get framerate from $FRAMERATE, falling back to 8 if not set
framerate = os.environ.get("FRAMERATE") or "8"
if int(framerate) not in range(1,16):
    print("Invalid framerate value {}. Must be between 1 and 16 inclusive.".format(framerate))
    exit()

# Get size from $SIZE, falling back to 1024 if not set
# Valid sizes are 512, 768 and 1024.
size = os.environ.get("SIZE") or "1024"
if int(size) not in [512, 768, 1024, 2048]:
    print(f"Invalid size {size}. Must be one of 512, 768, 1024, 2048.")
    stop_comfyui()
    sys.exit(1)

# Get steps from $STEPS, falling back to default_steps if not set
# Valid range is 5 to 200 inclusive
steps = os.environ.get("STEPS") or default_steps
if int(steps) not in range(5, 201):
    print(f"Invalid number of steps ({steps}). Valid range is 5 to 200 inclusive.")
    stop_comfyui()
    sys.exit(1)

# Get videosteps from $VIDEOSTEPS, falling back to default_steps if not set
# Valid range is from 5 to 40 inclusive
videosteps = os.environ.get("VIDEOSTEPS") or video_default_steps
if int(videosteps) not in range(5, 71):
    print(f"Invalid number of video steps ({videosteps}). Valid range is from 5 to 70 inclusive.")
    stop_comfyui()
    sys.exit(1)

# Get batch size from $BATCHING, falling back to 1 if not set
batching = os.environ.get("BATCHING") or batching
if int(batching) not in [1, 2, 4, 8]:
    print(f"Invalid batch size {batching}. Must be one of 1, 2, 4, 8.")
    stop_comfyui()
    sys.exit(1)

# Get sampler name from $SAMPLER, falling back to "euler_ancestral" if not set
sampler = os.environ.get("SAMPLER") or "euler_ancestral"
if sampler not in KSAMPLER_NAMES:
    print(f"Invalid sampler {sampler}. Must be one of euler, euler_ancestral, heun, heunpp2, dpm_2, dpm_2_ancestral, lms, dpm_fast, dpm_adaptive, dpmpp_2s_ancestral, dpmpp_sde, dpmpp_sde_gpu, dpmpp_2m, dpmpp_2m_sde, dpmpp_2m_sde_gpu, dpmpp_3m_sde, dpmpp_3m_sde_gpu, ddpm, lcm.")
    stop_comfyui()
    sys.exit(1)

# Get video sampler name from $VIDEO_SAMPLER, falling back to "euler_ancestral" if not set
videosampler = os.environ.get("VIDEOSAMPLER") or "euler_ancestral"
if videosampler not in KSAMPLER_NAMES:
    print(f"Invalid video sampler {videosampler}. Must be one of euler, euler_ancestral, heun, heunpp2, dpm_2, dpm_2_ancestral, lms, dpm_fast, dpm_adaptive, dpmpp_2s_ancestral, dpmpp_sde, dpmpp_sde_gpu, dpmpp_2m, dpmpp_2m_sde, dpmpp_2m_sde_gpu, dpmpp_3m_sde, dpmpp_3m_sde_gpu, ddpm, lcm.")
    stop_comfyui()
    sys.exit(1)

# Get scheduler name from $SCHEDULER, falling back to "normal" if not set
scheduler = os.environ.get("SCHEDULER") or "normal"
if scheduler not in SCHEDULER_NAMES:
    print(f"Invalid scheduler {scheduler}. Must be one of normal, karras, exponential, sgm_uniform, simple, ddim_uniform.")
    stop_comfyui()
    sys.exit(1)

# Get video scheduler name from $VIDEO_SCHEDULER, falling back to "normal" if not set
videoscheduler = os.environ.get("VIDEOSCHEDULER") or "normal"
if videoscheduler not in SCHEDULER_NAMES:
    print(f"Invalid video scheduler {videoscheduler}. Must be one of normal, karras, exponential, sgm_uniform, ddim_uniform.")
    stop_comfyui()
    sys.exit(1)


# give some easy-to-remember names to the nodes
prompt_pos_node = prompt_workflow["18"]
empty_latent_img_node = prompt_workflow["22"]
image_chkpoint_loader_node = prompt_workflow["16"]
video_chkpoint_loader_node = prompt_workflow["15"]
image_ksampler_node = prompt_workflow["17"]
video_ksampler_node = prompt_workflow["3"]
save_image_webp_node = prompt_workflow["10"]
save_image_apng_node = prompt_workflow["24"]

# set image dimensions and batch size in EmptyLatentImage node
empty_latent_img_node["inputs"]["width"] = size
empty_latent_img_node["inputs"]["height"] = size
empty_latent_img_node["inputs"]["batch_size"] = batching

# set the text prompt for positive CLIPTextEncode node
prompt_pos_node["inputs"]["text"] = prompt

# set the seed in KSampler node for the image
image_ksampler_node["inputs"]["seed"] = seed

# set the seed in KSampler node for the video
image_ksampler_node["inputs"]["seed"] = videoseed

# set the steps in KSampler node for the image
image_ksampler_node["inputs"]["steps"] = steps

# set the steps in KSampler node for the video
video_ksampler_node["inputs"]["steps"] = videosteps

# set the sampler name in KSampler node for the image
image_ksampler_node["inputs"]["sampler_name"] = sampler

# set the sampler name in KSampler node for the video
video_ksampler_node["inputs"]["sampler_name"] = videosampler

# set the scheduler name in KSampler node for the image
image_ksampler_node["inputs"]["scheduler"] = scheduler

# set the scheduler name in KSampler node for the image
video_ksampler_node["inputs"]["scheduler"] = videoscheduler

# set the filename output prefix
save_image_webp_node["inputs"]["filename_prefix"] = "output"
save_image_webp_node["inputs"]["framerate"] = framerate
save_image_apng_node["inputs"]["filename_prefix"] = "output"
save_image_apng_node["inputs"]["framerate"] = framerate

# everything set, add entire workflow to queue.
queue_prompt(prompt_workflow)

# Wait for the prompt to finish
def check_queue_status():
    try:
        response = requests.get("http://127.0.0.1:8188/queue", timeout=5)
        if response is None or response.status_code != 200:
            if response:
                print(f"Server not ready ({response.status_code}). Waiting 1 second...")
            else:
                print("Server not ready (no response). Waiting 1 second...")
            return "NOTREADY"
        else:
            return response.json()
    except requests.exceptions.RequestException as e:
        print("Server not ready (requests raised an exception). Waiting 1 second...")
        return "NOTREADY"

# Check the queue status
queue_status = check_queue_status()
timeout = 900 # If prompt doesn't finish within 900 seconds, we'll give up
start_time = time.time()
timer = start_time
while timer - start_time < timeout:
    queue_status = check_queue_status()
    if queue_status == {"queue_running": [], "queue_pending": []}:
        print("Prompt finished successfully.")
        break
    else:
        print("[DEBUG] Prompt is still running. Waiting 1 second...")
        time.sleep(1)
        timer = time.time()
else:
    print("Prompt is still running or there was an error.")
    # Kill the ComfyUI server and exit with an error
    stop_comfyui()
    sys.exit(1)

# We made it!
# Kill the ComfyUI server and exit cleanly.
stop_comfyui()
exit(0)
