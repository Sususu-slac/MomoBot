from pathlib import Path
import os,sys,json

ROOT=Path(__file__).resolve().parents[1]
STATE_ROOT=Path(os.environ.get('MOMOBOT_STATE_ROOT',str(ROOT)))
STATE_ROOT.mkdir(parents=True,exist_ok=True)
RECON=Path(os.environ.get('BL62_RECON_ROOT','D:/BL62_Reconstruction_GUI'))
FINETUNE=Path('D:/BL62_Finetune_GUI')
CONDA=Path(os.environ.get('BL62_CONDA_ENVS',str(Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))/'miniforge3/envs')))
GUI_PYTHON=CONDA/'BL62_Studio/python.exe'
RECON_PYTHON=CONDA/'tomocupy_astra/python.exe'
SAM3_PYTHON=CONDA/'SAM3p1/python.exe'
MODEL_DIR=Path(os.environ.get('BL62_MODEL_DIR','D:/Chcekpoints/LLM'))
GEMMA_MODEL=MODEL_DIR/'gemma-4-26B_q4_0-it.gguf'
MODEL=GEMMA_MODEL
DEFAULT_PROFILE='gemma4'
VERSION='0.10.1'
RUNTIME_ROOT=Path(os.environ.get('MOMOBOT_RUNTIME_ROOT',str(ROOT/'runtime/llama-b11988')))
MODEL_PROFILES={
    'gemma4':dict(label='Gemma 4 26B-A4B · Google · GPU 1',mode='GPU 1',model_path=GEMMA_MODEL,context=8192,
        options=dict(adapter='chat',thinking='off',template_kwargs={'enable_thinking':False},max_output_tokens=768))}
SAM3_CHECKPOINT='D:/Chcekpoints/checkpoint_demo_05142026.pt'
SAMPLE='D:/1_Datasets/2_Tomography/hdf5_collection/NMC811_Rod.hdf5'
IMAGES='C:/Users/subo/Desktop/Science_data/Labeled_data/sample_2/training_dataset/images'

DEFAULTS=dict(input_hdf5='',image_folder='',dataset='',output_root=str(STATE_ROOT/'outputs/jobs'),
    checkpoint=SAM3_CHECKPOINT,resume_checkpoint='',gpu=0,center=0.0,start_row=1021,end_row=1026,
    method='fourierrec',remove_stripe_method='vo-all',geometry='tomography',lamino_angle=20.0,binning=0,chunk_size=4,iterations=20,
    prompt='particle',prompt_mode='text',instance_reference={},confidence=.2,nms_iou=.5,max_images=0,segment_all=False,
    range_low=None,range_high=None,initial_step=None,target_step=.25,search_row=None,
    epochs=1,batch_size=1,workers=2,val_every=1,save_every=0,lr_scale=.05,train_percent=80,seed=42,
    training_python='/home/subo/miniforge3/envs/sam3_finetune_wsl/bin/python',training_repo='/home/subo/sam3',
    training_template='/home/subo/sam3/sam3/train/configs/roboflow_v100/roboflow_v100_full_ft_100_images.yaml',
    distro='Ubuntu-24.04',sam3_repo='D:/SAM3p1/sam3',trial_row=None,trial_width=10.,trial_step=1.)

def load_preferences():
    try:return json.loads((STATE_ROOT/'settings.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}

def save_preferences(value):
    temporary=STATE_ROOT/'settings.tmp';temporary.write_text(json.dumps(value,indent=2),encoding='utf-8');temporary.replace(STATE_ROOT/'settings.json')
