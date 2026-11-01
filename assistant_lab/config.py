from pathlib import Path
import os,sys,json

ROOT=Path(__file__).resolve().parents[1]
RECON=Path('D:/BL62_Reconstruction_GUI')
FINETUNE=Path('D:/BL62_Finetune_GUI')
CONDA=Path(os.environ.get('LOCALAPPDATA','C:/Users/subo/AppData/Local'))/'miniforge3/envs'
GUI_PYTHON=CONDA/'BL62_Studio/python.exe'
RECON_PYTHON=CONDA/'tomocupy_astra/python.exe'
SAM3_PYTHON=CONDA/'SAM3p1/python.exe'
MODEL=Path('D:/Chcekpoints/LLM/Qwen3.8-27B-Q4_K_M.gguf')
FALLBACK_MODEL=Path('D:/Chcekpoints/LLM/Qwen3-4B-Instruct-2507-Q4_K_M.gguf')
RUNTIME_ROOT=ROOT/'runtime/llama-b11988'
MODEL_PROFILES={
    'primary':dict(label='Qwen3.8-27B · GPU 1',mode='GPU 1',model_path=MODEL,context=8192),
    'fallback':dict(label='Qwen3-4B · CPU',mode='CPU',model_path=FALLBACK_MODEL,context=4096)}
SAM3_CHECKPOINT='D:/Chcekpoints/checkpoint_demo_05142026.pt'
SAMPLE='D:/1_Datasets/2_Tomography/hdf5_collection/NMC811_Rod.hdf5'
IMAGES='C:/Users/subo/Desktop/Science_data/Labeled_data/sample_2/training_dataset/images'

DEFAULTS=dict(input_hdf5='',image_folder='',dataset='',output_root=str(ROOT/'outputs/jobs'),
    checkpoint=SAM3_CHECKPOINT,resume_checkpoint='',gpu=0,center=0.0,start_row=1021,end_row=1026,
    method='fourierrec',geometry='tomography',lamino_angle=20.0,binning=0,chunk_size=4,iterations=20,
    prompt='particle',confidence=.2,nms_iou=.5,max_images=0,segment_all=False,
    range_low=None,range_high=None,initial_step=None,target_step=.25,search_row=None,
    epochs=1,batch_size=1,workers=2,val_every=1,save_every=0,lr_scale=.05,train_percent=80,seed=42,
    training_python='/home/subo/miniforge3/envs/sam3_finetune_wsl/bin/python',training_repo='/home/subo/sam3',
    training_template='/home/subo/sam3/sam3/train/configs/roboflow_v100/roboflow_v100_full_ft_100_images.yaml',
    distro='Ubuntu-24.04',sam3_repo='D:/SAM3p1/sam3',trial_row=None,trial_width=10.,trial_step=1.)

def load_preferences():
    try:return json.loads((ROOT/'settings.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}

def save_preferences(value):
    temporary=ROOT/'settings.tmp';temporary.write_text(json.dumps(value,indent=2),encoding='utf-8');temporary.replace(ROOT/'settings.json')
