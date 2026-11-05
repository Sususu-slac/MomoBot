"""Nonmodal, read-only image browsers with explicit parameter/selection handoff."""
from __future__ import annotations
import copy,math,re
from collections import OrderedDict
from pathlib import Path
import h5py,numpy as np,tifffile
from PIL import Image
from PySide6.QtCore import Qt,QObject,QRunnable,QThreadPool,Signal,QTimer,QLineF
from PySide6.QtGui import QImage,QPixmap,QPainter,QPen,QColor
from PySide6.QtWidgets import (QDialog,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QPushButton,
 QComboBox,QCheckBox,QLineEdit,QSpinBox,QDoubleSpinBox,QSlider,QSplitter,QScrollArea,QGraphicsView,QGraphicsScene,QListWidget,QSizePolicy)


def file_stamp(path):
    s=Path(path).stat();return [s.st_size,s.st_mtime_ns]


def read_hdf5(path,source,index,expected):
    if file_stamp(path)!=expected:raise ValueError('The input changed. Reload it in MomoBot before using this viewer.')
    keys={'Projection':'exchange/data','Flat':'exchange/data_white','Dark':'exchange/data_dark'}
    with h5py.File(path,'r') as h:
        ds=h[keys[source]]
        if ds.ndim==2:a=np.asarray(ds[:]);index=0
        else:a=np.asarray(ds[max(0,min(index,ds.shape[0]-1))])
    if file_stamp(path)!=expected:raise ValueError('The input changed while reading.')
    return a


def read_image(path):
    if Path(path).suffix.lower() in ('.tif','.tiff'):
        with tifffile.TiffFile(path) as t:
            page=t.pages[0]
            if len(page.shape)!=2:raise ValueError('This browser expects 2D reconstruction slices, not a packed 3D TIFF.')
            return page.asarray()
    with Image.open(path) as image:
        a=np.asarray(image)
        if a.ndim==3:a=a[...,:3].astype(np.float32).mean(axis=2)
        return a


def image_files(folder):
    # A worker may put its TIFFs in a named subfolder. Do not include masks/plots.
    folder=Path(folder)
    if not folder.is_dir():return []
    files=list(folder.rglob('*.tiff'))+list(folder.rglob('*.tif'))
    if not files:files=[p for p in folder.iterdir() if p.suffix.lower() in ('.png','.jpg','.jpeg','.bmp') and p.is_file()]
    def key(p):return [int(x) if x.isdigit() else x.casefold() for x in re.split(r'(\d+)',str(p.relative_to(folder)))]
    return sorted(set(files),key=key)

class ReadSignals(QObject):ready=Signal(object)
class ReadTask(QRunnable):
    def __init__(self,key,call):super().__init__();self.key=key;self.call=call;self.signals=ReadSignals()
    def run(self):
        try:
            a=np.asarray(self.call());shape=a.shape;dtype=str(a.dtype)
            if a.ndim!=2:raise ValueError('The selected image must be 2D.')
            stride=max(1,math.ceil(max(a.shape)/1536));a=np.ascontiguousarray(a[::stride,::stride],dtype=np.float32)
            finite=a[np.isfinite(a)]
            if not finite.size:raise ValueError('No finite pixels in this image.')
            low,high=map(float,np.percentile(finite,[1,99.5]));high=high if high>low else low+1
            result=(self.key,a,(low,high),shape,dtype,None)
        except Exception as error:result=(self.key,None,None,None,None,str(error))
        self.signals.ready.emit(result)

class ScanTask(QRunnable):
    def __init__(self,folder):super().__init__();self.folder=folder;self.signals=ReadSignals()
    def run(self):
        try:self.signals.ready.emit((image_files(self.folder),None))
        except Exception as error:self.signals.ready.emit(([],str(error)))

class Canvas(QGraphicsView):
    row_picked=Signal(float)
    def __init__(self):
        super().__init__();self.setScene(QGraphicsScene(self));self.setDragMode(QGraphicsView.ScrollHandDrag);self.setRenderHint(QPainter.SmoothPixmapTransform);self.item=None;self.row_marks=[];self.saved_view=None;self.press_position=None;self.setMinimumSize(360,300);self.setToolTip('Wheel: zoom. Drag: pan. In the input viewer, click a projection to choose the search row.')
    def clear_image(self):
        if self.item:self.saved_view=(self.item.pixmap().size(),self.transform(),self.mapToScene(self.viewport().rect().center()))
        self.scene().clear();self.item=None
    def show_gray(self,gray):
        image=QImage(gray.data,gray.shape[1],gray.shape[0],gray.strides[0],QImage.Format_Grayscale8).copy();pixmap=QPixmap.fromImage(image)
        first=self.item is None
        if first:self.item=self.scene().addPixmap(pixmap)
        else:self.item.setPixmap(pixmap)
        self.scene().setSceneRect(self.item.boundingRect())
        if first:
            if self.saved_view and self.saved_view[0]==pixmap.size():self.setTransform(self.saved_view[1]);self.centerOn(self.saved_view[2])
            else:self.fit_image()
    def fit_image(self):
        if self.item:self.fitInView(self.item,Qt.KeepAspectRatio)
    def mousePressEvent(self,event):self.press_position=event.position();super().mousePressEvent(event)
    def mouseReleaseEvent(self,event):
        super().mouseReleaseEvent(event)
        if event.button()==Qt.LeftButton and self.item and self.press_position is not None and (event.position()-self.press_position).manhattanLength()<4:
            point=self.mapToScene(event.position().toPoint());rect=self.item.boundingRect()
            if rect.contains(point):self.row_picked.emit(point.y()/rect.height())
    def drawForeground(self,painter,rect):
        if self.item:
            bounds=self.item.boundingRect()
            for fraction,color in self.row_marks:
                pen=QPen(QColor(color));pen.setCosmetic(True);painter.setPen(pen);y=fraction*bounds.height();painter.drawLine(QLineF(bounds.left(),y,bounds.right(),y))
    def wheelEvent(self,event):self.scale(1.2 if event.angleDelta().y()>0 else 1/1.2,1.2 if event.angleDelta().y()>0 else 1/1.2);event.accept()

class ImageBrowser(QDialog):
    def __init__(self,parent,title):
        super().__init__(parent);self.setWindowTitle(title);self.setAttribute(Qt.WA_DeleteOnClose);self.setModal(False);self.resize(1180,800)
        self.closed=False;self.loading=False;self.pending=None;self.request_key=None;self.array=None;self.cache=OrderedDict();self.auto_limits=None;self.loaded_key=None
        self.layout_=QVBoxLayout(self);self.path_label=QLabel();self.path_label.setTextFormat(Qt.PlainText);self.path_label.setWordWrap(True);self.layout_.addWidget(self.path_label)
        self.split=QSplitter();self.layout_.addWidget(self.split,1);self.left=QWidget();self.left_layout=QVBoxLayout(self.left);self.left.setMaximumWidth(340);self.split.addWidget(self.left)
        right=QWidget();v=QVBoxLayout(right);self.canvas=Canvas();v.addWidget(self.canvas,1)
        nav=QHBoxLayout();self.previous=QPushButton('Previous');self.next=QPushButton('Next');self.frame=QSpinBox();self.frame.setMinimum(1);self.frame.setMaximum(1);self.slider=QSlider(Qt.Horizontal);self.slider.setRange(1,1);self.count_label=QLabel('/ 0')
        for item in (self.previous,self.frame,self.count_label,self.next):nav.addWidget(item)
        nav.addWidget(self.slider,1);v.addLayout(nav);self.previous.clicked.connect(lambda:self.frame.setValue(self.frame.value()-1));self.next.clicked.connect(lambda:self.frame.setValue(self.frame.value()+1));self.frame.valueChanged.connect(self.slider.setValue);self.slider.valueChanged.connect(self.frame.setValue)
        contrast=QHBoxLayout();self.low=QDoubleSpinBox();self.high=QDoubleSpinBox()
        for spin in (self.low,self.high):spin.setRange(-1e100,1e100);spin.setFixedWidth(140);spin.setDecimals(5);spin.valueChanged.connect(self.draw)
        contrast.addWidget(QLabel('Low'));contrast.addWidget(self.low);contrast.addWidget(QLabel('High'));contrast.addWidget(self.high);auto=QPushButton('Auto');auto.clicked.connect(self.auto);contrast.addWidget(auto);fit=QPushButton('Fit');fit.clicked.connect(self.canvas.fit_image);contrast.addWidget(fit);self.lock_display=QCheckBox('Lock');self.lock_display.setToolTip('Keep the display range when changing images');contrast.addWidget(self.lock_display);self.has_display_range=False;v.addLayout(contrast)
        self.image_info=QLabel();self.image_info.setTextFormat(Qt.PlainText);self.image_info.setWordWrap(True);v.addWidget(self.image_info);self.split.addWidget(right);self.split.setSizes([320,860])
        self.status=QLabel();self.status.setWordWrap(True);self.status.setTextFormat(Qt.PlainText);self.layout_.addWidget(self.status)
        self.debounce=QTimer(self);self.debounce.setSingleShot(True);self.debounce.setInterval(100);self.debounce.timeout.connect(self.start_read)
    def request(self,key,call):
        self.request_key=key;self.pending=(key,call);self.array=None;self.loaded_key=None;self.canvas.clear_image();self.status.setText('Loading preview…');self.debounce.start()
    def start_read(self):
        if self.closed or self.loading or not self.pending:return
        key,call=self.pending;self.pending=None
        if key in self.cache:self.cache.move_to_end(key);self.loaded(self.cache[key]);return
        task=ReadTask(key,call);task.signals.ready.connect(self.loaded);self.loading=True;QThreadPool.globalInstance().start(task)
    def loaded(self,result):
        self.loading=False
        if self.closed:return
        key,array,limits,shape,dtype,error=result
        if key==self.request_key:
            if error:self.status.setText('Preview unavailable: '+error)
            else:
                self.cache[key]=result
                while len(self.cache)>4:self.cache.popitem(last=False)
                self.array=array;self.loaded_key=key;self.auto_limits=limits;self.image_info.setText(f'{shape[1]} × {shape[0]} · {dtype} · display preview only');self.status.setText('');self.draw() if self.has_display_range and self.lock_display.isChecked() else self.auto();self.preview_ready()
        if self.pending:self.start_read()
    def preview_ready(self):pass
    def auto(self):
        if self.auto_limits:
            self.has_display_range=True
            self.low.blockSignals(True);self.high.blockSignals(True);decimals=max(4,min(50,int(4-math.floor(math.log10(self.auto_limits[1]-self.auto_limits[0])))));self.low.setDecimals(decimals);self.high.setDecimals(decimals);self.low.setValue(self.auto_limits[0]);self.high.setValue(self.auto_limits[1]);self.low.blockSignals(False);self.high.blockSignals(False);self.draw()
    def draw(self):
        if self.array is None:return
        lo,hi=self.low.value(),self.high.value()
        if hi<=lo:return
        gray=np.nan_to_num(np.clip((self.array-lo)/(hi-lo),0,1),nan=0,posinf=1,neginf=0);self.canvas.show_gray(np.ascontiguousarray(gray*255,dtype=np.uint8))
    def navigation(self,count):
        self.frame.setEnabled(count>0);self.slider.setEnabled(count>0);self.previous.setEnabled(count>0);self.next.setEnabled(count>0);self.frame.setMaximum(max(count,1));self.slider.setMaximum(max(count,1));self.count_label.setText(f'/ {count}')
    def closeEvent(self,event):self.closed=True;self.debounce.stop();self.pending=None;self.cache.clear();event.accept()

class InputBrowser(ImageBrowser):
    apply_requested=Signal(object)
    def __init__(self,parent,task,tool):
        super().__init__(parent,'MomoBot — Input data');self.snapshot=copy.deepcopy(task);self.tool=tool;self.path=tool['source'];self.meta=tool['metadata'];s=task['settings'];p=task.get('sop',{});self.path_label.setText(self.path)
        self.source=QComboBox();self.source.addItems(['Projection','Flat','Dark']);self.left_layout.addWidget(self.source)
        details=QLabel(f"{self.meta['projections']} projections\nDetector {self.meta['rows']} × {self.meta['width']}\n{self.meta.get('dtype','')}\nTheta {self.meta.get('theta_min','?')}–{self.meta.get('theta_max','?')} {self.meta.get('theta_unit','')}");details.setWordWrap(True);self.left_layout.addWidget(details)
        panel=QWidget();form=QFormLayout(panel);form.setContentsMargins(2,2,2,2);form.setHorizontalSpacing(8);form.setRowWrapPolicy(QFormLayout.WrapLongRows);scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(panel);self.left_layout.addWidget(scroll,1);self.fields={}
        self.geometry=QComboBox();self.geometry.addItems(['Not set','Tomography','Laminography']);self.geometry.setCurrentIndex((1 if s['geometry']=='tomography' else 2) if p.get('geometry_confirmed') else 0);form.addRow('Geometry',self.geometry)
        self.mode=QComboBox();self.mode.addItems(['Keep chat workflow','Traditional','Smart']);self.mode.setCurrentIndex({'manual':1,'auto':2}.get(p.get('mode'),0));form.addRow('Workflow',self.mode)
        def number(key,label,low,high,integer=False,default=None):
            box=QSpinBox() if integer else QDoubleSpinBox();box.setRange(low,high)
            if not integer:box.setDecimals(4)
            value=s.get(key) if default is None else default;box.setValue(value or 0);self.fields[key]=box;form.addRow(label,box);return box
        number('lamino_angle','Tilt angle (°)',-89.9,89.9,default=s['lamino_angle'] if p.get('angle_confirmed') else 0)
        self.method=QComboBox();self.method.addItems(['fourierrec','linerec','lprec','fbp_cuda','sirt_cuda','cgls_cuda']);self.method.setCurrentText(s['method']);form.addRow('Method',self.method)
        number('center','Center / anchor (px)',0,self.meta['width']-0.001)
        number('start_row','Start row (0-based)',0,self.meta['rows']-1,True);number('end_row','End row (exclusive)',1,self.meta['rows'],True)
        number('search_row','Search row (0-based)',0,self.meta['rows']-1,True,default=s.get('trial_row') if s.get('trial_row') is not None else s.get('search_row') if s.get('search_row') is not None else self.meta['rows']//2)
        number('trial_width','Trial half-width',.01,self.meta['width']);number('trial_step','Trial step',.01,self.meta['width'])
        self.binning=QComboBox();self.binning.addItems(['1×1','2×2','4×4','8×8']);self.binning.setCurrentIndex(s['binning']);form.addRow('Binning',self.binning)
        number('gpu','GPU',0,1,True)
        self.prompt=QLineEdit(s['prompt'] if p.get('target_confirmed') and s.get('prompt_mode')=='text' else '');form.addRow('Text feature',self.prompt)
        self.stripes=QComboBox();self.stripes.addItems(['vo-all','none','fw','ti']);self.stripes.setCurrentText(s.get('remove_stripe_method','vo-all'));form.addRow('Remove stripes',self.stripes);number('dezinger','Dezinger',0,100,True)
        self.apply_button=QPushButton('Apply to Momo');self.apply_button.setObjectName('primary');self.left_layout.addWidget(self.apply_button);self.apply_button.clicked.connect(self.apply)
        for field in list(self.fields.values())+[self.geometry,self.mode,self.method,self.binning,self.prompt,self.stripes]:field.setMinimumWidth(95);field.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Fixed)
        self.initial=self.values();self.initial_geometry=self.geometry.currentIndex();self.initial_mode=self.mode.currentIndex();self.source.currentIndexChanged.connect(self.configure_source);self.frame.valueChanged.connect(self.show_frame)
        for key in ('start_row','end_row','search_row'):self.fields[key].valueChanged.connect(self.update_rows)
        self.canvas.row_picked.connect(self.pick_row);self.update_rows();self.configure_source()
    def update_rows(self):
        self.canvas.row_marks=[(self.fields[k].value()/self.meta['rows'],color) for k,color in (('start_row','#4bbf86'),('end_row','#4bbf86'),('search_row','#ffbe46'))];self.canvas.viewport().update()
    def pick_row(self,fraction):
        if self.source.currentText()=='Projection':self.fields['search_row'].setValue(min(self.meta['rows']-1,int(fraction*self.meta['rows'])))
    def values(self):
        values={k:v.value() for k,v in self.fields.items()};values.update(method=self.method.currentText(),binning=self.binning.currentIndex(),remove_stripe_method=self.stripes.currentText(),prompt=self.prompt.text().strip());return values
    def apply(self):
        values=self.values();updates={k:v for k,v in values.items() if v!=self.initial[k]}
        if self.geometry.currentIndex() and self.geometry.currentIndex()!=self.initial_geometry:updates['geometry']='tomography' if self.geometry.currentIndex()==1 else 'laminography'
        if updates.get('geometry')=='laminography':updates['lamino_angle']=values['lamino_angle']
        if updates.get('geometry')=='tomography':updates.pop('lamino_angle',None)
        if 'search_row' in updates:updates['trial_row']=updates['search_row']
        mode={0:'unchanged',1:'manual',2:'auto'}[self.mode.currentIndex()] if self.mode.currentIndex()!=self.initial_mode else 'unchanged'
        if not updates and mode=='unchanged':self.status.setText('No parameter changes. You can keep browsing or close this window.');return
        self.apply_requested.emit({'updates':updates,'mode':mode})
    def configure_source(self):
        source=self.source.currentText();shape=self.meta.get('white_shape') if source=='Flat' else self.meta.get('dark_shape') if source=='Dark' else [self.meta['projections']]
        count=shape[0] if len(shape)==3 or source=='Projection' else 1
        self.navigation(count);self.frame.setValue(max(1,count//2+1));self.show_frame()
    def show_frame(self):
        source,index=self.source.currentText(),self.frame.value()-1
        self.request((self.path,source,index,tuple(self.tool['source_stat'])),lambda:read_hdf5(self.path,source,index,self.tool['source_stat']))

class ResultBrowser(ImageBrowser):
    select_requested=Signal(object)
    def __init__(self,parent,tool,items=None):
        trial=tool['kind']=='trials';super().__init__(parent,'MomoBot — Trial results' if trial else 'MomoBot — Reconstruction browser');self.tool=tool;self.lock_display.setChecked(True);self.trial=trial;self.can_select=True;self.items=copy.deepcopy(items or []);self.path_label.setText(tool['source']);self.current_file_stamp=None;self.scanning=False
        self.files_list=QListWidget();self.left_layout.addWidget(self.files_list,1);self.use_button=QPushButton('Use this angle' if self.items and self.items[0].get('quantity')=='angle' else 'Use this center');self.use_button.setObjectName('primary');self.use_button.setEnabled(False);self.left_layout.addWidget(self.use_button);self.use_button.setVisible(trial);self.use_button.clicked.connect(self.select)
        refresh=QPushButton('Refresh');self.left_layout.addWidget(refresh);refresh.clicked.connect(self.refresh);self.refresh_timer=QTimer(self);self.refresh_timer.setInterval(2000);self.refresh_timer.timeout.connect(self.refresh)
        self.frame.valueChanged.connect(self.show_frame);self.files_list.currentRowChanged.connect(lambda row:self.frame.setValue(row+1) if row>=0 else None)
        self.refresh()
        if not trial:self.refresh_timer.start()
    def refresh(self):
        if self.closed:return
        if not self.trial:
            if self.scanning:return
            self.scanning=True;task=ScanTask(self.tool['source']);task.signals.ready.connect(self.scan_ready);QThreadPool.globalInstance().start(task);return
        self.populate();self.show_frame()
    def scan_ready(self,result):
        self.scanning=False
        if self.closed:return
        files,error=result
        if error:self.status.setText(error);return
        new=[dict(file=str(p)) for p in files]
        if new==self.items:
            if not new:self.status.setText('Waiting for reconstruction slices. This view refreshes automatically.')
            elif self.array is None:self.show_frame()
            return
        current=self.items[self.frame.value()-1]['file'] if self.items and self.frame.value()<=len(self.items) else None
        self.items=new;self.populate()
        if current:self.frame.setValue(next((n for n,item in enumerate(self.items,1) if item['file']==current),1))
        self.show_frame()
    def populate(self):
        self.files_list.blockSignals(True);self.files_list.clear()
        for n,item in enumerate(self.items,1):self.files_list.addItem(f"{item.get('index',n)} · {item['value']:g} {'°' if item.get('quantity')=='angle' else 'px'}" if self.trial else Path(item['file']).name)
        self.files_list.blockSignals(False);self.navigation(len(self.items))
    def show_frame(self):
        self.use_button.setEnabled(False)
        if not self.items:return
        index=min(self.frame.value()-1,len(self.items)-1);self.files_list.blockSignals(True);self.files_list.setCurrentRow(index);self.files_list.blockSignals(False);item=self.items[index];path=item['file']
        try:stamp=file_stamp(path)
        except OSError as error:self.status.setText(str(error));self.canvas.clear_image();return
        self.current_file_stamp=stamp;self.request((path,tuple(stamp)),lambda:read_image(path))
    def preview_ready(self):
        self.use_button.setEnabled(self.trial and self.can_select);item=self.items[self.frame.value()-1];self.image_info.setText(self.image_info.text()+'\n'+Path(item['file']).name)
    def select(self):
        if not self.trial or self.array is None or self.loaded_key!=self.request_key:return
        item=self.items[self.frame.value()-1]
        try:unchanged=file_stamp(item['file'])==self.current_file_stamp
        except OSError:unchanged=False
        if not unchanged:self.status.setText('This candidate changed or is missing. Reload it before selecting.');return
        self.select_requested.emit(copy.deepcopy(item))
    def closeEvent(self,event):self.refresh_timer.stop();super().closeEvent(event)
