import sys,json,copy,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from assistant_lab.chat_model import ChatModel
from assistant_lab.conversations import *
from assistant_lab.config import ROOT

def task(kind,current):
 t=new_task()
 if kind:choose_kind(t,kind)
 if current not in ('kind','input_hdf5','image_folder','dataset'):
  field='image_folder' if kind=='segment' else 'dataset' if kind in ('train','prepare_dataset') else 'input_hdf5'
  set_source(t,field,'D:/selected');accept_source(t,field,'D:/selected',{'rows':2048,'width':2048,'projections':901} if field=='input_hdf5' else {'images':12,'needs_split':current=='split'})
 if current=='center':t['center_mode']='known'
 if current=='rows':t['center_mode']='known';t['settings']['center']=1028.75
 if current=='limit':mark(t,'prompt')
 if current=='epochs':t['needs_split']=False
 return t
CASES=[
 (None,'kind','I want to reconstruct tomography data.','reconstruct',{}),
 (None,'kind','I want to segment images.','segment',{}),
 (None,'kind','I want to fine-tune SAM3.','train',{}),
 ('reconstruct','center','1028.75','set_parameters',{'center':1028.75}),
 ('reconstruct','center_mode','Find the center automatically.','set_parameters',{}),
 ('reconstruct','rows','Five middle slices please.','set_parameters',{}),
 ('reconstruct','rows','All slices.','set_parameters',{}),
 ('reconstruct','rows','Start row 1023 and end row 1025.','set_parameters',{'start_row':1023,'end_row':1025}),
 ('segment','prompt','particle','set_parameters',{'prompt':'particle'}),
 ('segment','prompt','Look for nanoparticle.','set_parameters',{'prompt':'nanoparticle'}),
 ('segment','limit','all','set_parameters',{'max_images':0}),
 ('segment','limit','Only 1 image, with confidence 25 percent.','set_parameters',{'max_images':1,'confidence':.25}),
 ('train','epochs','2 epochs with batch size 1.','set_parameters',{'epochs':2,'batch_size':1}),
 ('train','epochs','Use the default.','set_parameters',{}),
 ('train','split','75% training and 25% validation with seed 7.','set_parameters',{'train_percent':75,'seed':7}),
 ('train','epochs','What does an epoch mean?','help',{}),
 ('reconstruct','center','Why does the center matter?','help',{}),
 ('segment','prompt','Set GPU to 0.','set_parameters',{'gpu':0}),
 ('segment','prompt','Delete my original pictures.','clarify',{}),
 ('reconstruct','center_mode','Automatically optimize the laminography angle.','clarify',{}),
]
model=ChatModel();report={'cases':[]}
try:
 model.start('GPU 1');model.wait_ready()
 for kind,current,text,expected,updates in CASES:
  t=task(kind,current);message(t,'assistant',question(t)[0]);message(t,'user',text)
  try:
   p,c,m=model.converse(text,t);passed=p.action==expected and p.updates==updates
   if 'automatically.' in text:passed=passed and c['center_mode']=='auto'
   if text=='Five middle slices please.':passed=passed and c['row_scope']=='middle'
   if text=='All slices.':passed=passed and c['row_scope']=='all'
   if text=='Use the default.':passed=passed and c['accept_defaults']
   row=dict(command=text,step=current,actual=p.to_dict(),control=c,seconds=m['seconds'],passed=passed)
  except Exception as e:row=dict(command=text,step=current,error=str(e),passed=False)
  report['cases'].append(row);print('PASS' if row['passed'] else 'FAIL',text,row.get('actual',row.get('error')),flush=True)
finally:model.stop()
report['passed']=sum(r['passed'] for r in report['cases']);report['total']=len(report['cases']);dest=ROOT/'test_outputs/chat_model_cases.json';dest.parent.mkdir(exist_ok=True);dest.write_text(json.dumps(report,indent=2),encoding='utf-8');print('REPORT',report['passed'],report['total'],flush=True)
