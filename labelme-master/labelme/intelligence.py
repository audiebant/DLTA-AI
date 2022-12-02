import json
import time
from inferencing import models_inference
from labelme.label_file import LabelFile
from labelme.shape import Shape
from labelme import PY2
from qtpy import QtCore
from qtpy.QtCore import Qt
from qtpy.QtCore import QThread
from qtpy.QtCore import Signal as pyqtSignal
from qtpy import QtGui
from qtpy import QtWidgets
import threading
import os
import os.path as osp
import warnings

import torch
from mmdet.apis import inference_detector, init_detector
warnings.filterwarnings("ignore")

class IntelligenceWorker(QThread):
    sinOut = pyqtSignal(int,int)
    def __init__(self, parent, images, source):
        super(IntelligenceWorker, self).__init__(parent)
        self.parent = parent
        self.source = source
        self.images = images

    def run(self):
        index = 0
        total = len(self.images)
        for filename in self.images:
            
            if self.parent.isVisible==False:
                return
            if self.source.operationCanceled==True:
                return
            index = index + 1
            json_name = osp.splitext(filename)[0] + ".json"
            # if os.path.exists(json_name)==False:
            
            if os.path.isdir(json_name):
                os.remove(json_name)
            
            try:
                print("Decoding "+filename)
                s = self.source.get_shapes_of_one(filename)
                self.source.saveLabelFile(filename, s)
            except Exception as e:
                print(e)
            self.sinOut.emit(index,total)

class Intelligence():
    def __init__(self,parent):
        self.reader = models_inference()
        self.parent = parent
        self.threshold = 0.3
        self.current_model_name , self.current_mm_model = self.make_mm_model("")
        
        
    def make_mm_model(self, selected_model_name):
        with open("saved_models.json") as json_file:
            data = json.load(json_file)
            if selected_model_name == "":
            # read the saved_models.json file and import the config and checkpoint files from the first model
                selected_model_name = list(data.keys())[0]
                config = data[selected_model_name]["config"]
                checkpoint = data[selected_model_name]["checkpoint"]
            else:
                config = data[selected_model_name]["config"]
                checkpoint = data[selected_model_name]["checkpoint"]
            print(f'selected model : {selected_model_name} \nconfig : {config}\ncheckpoint : {checkpoint} \n')
            
        torch.cuda.empty_cache()
        # model = init_detector("C:/Users/Shehab/Desktop/l001/ANNOTATION_TOOL/mmdetection/mmdetection/configs/detectors/htc_r50_sac_1x_coco.py", 
        #                     "C:/Users/Shehab/Desktop/l001/ANNOTATION_TOOL/mmdetection/mmdetection/checkpoints/htc_r50_sac_1x_coco-bfa60c54.pth", device = torch.device("cuda"))
        model = init_detector(config, 
                            checkpoint, device = torch.device("cuda"))
        # "C:\Users\Shehab\Desktop\l001\ANNOTATION_TOOL\mmdetection\mmdetection\configs\yolact\yolact_r50_1x8_coco.py"
        # model = init_detector("C:/Users/Shehab/Desktop/mmdetection/mmdetection/configs/detectors/htc_r50_sac_1x_coco.py",
                            # "C:/Users/Shehab/Desktop/mmdetection/mmdetection/checkpoints/htc_r50_sac_1x_coco-bfa60c54.pth", device = torch.device("cuda"))
        return selected_model_name, model   
        
    def get_shapes_of_one(self,filename):
        # print(f"Threshold is {self.threshold}")
        # results = self.reader.decode_file(img_path = filename, threshold = self.threshold , selected_model_name = self.current_model_name)["results"]
        start_time = time.time()
        print(filename)
        results = self.reader.decode_file(img_path = filename, model = self.current_mm_model,threshold = self.threshold )["results"]
        end_time = time.time()
        print(f"Time taken to annoatate img on {self.current_model_name}: {end_time - start_time}")

        shapes = []
        for result in results:
            shape = Shape()
            shape.label = result["class"]
            shape.content = result["confidence"]
            shape.shape_type="polygon"
            shape.flags = {}
            shape.other_data = {}
            for i in range(len(result["seg"])):
                x = result["seg"][i][0]
                y = result["seg"][i][1]
                shape.addPoint(QtCore.QPointF(x, y))
            shape.close()
            shapes.append(shape)
            #self.addLabel(shape)
        return shapes
        
    def get_shapes_of_batch(self,images):
        self.pd = self.startOperationDialog()
        self.thread = IntelligenceWorker(self.parent,images,self)
        self.thread.sinOut.connect(self.updateDialog)
        self.thread.start()



    # get the thresold as input from the user
    def setThreshold(self):
        text, ok = QtWidgets.QInputDialog.getText(self.parent, 'Threshold Selector', 'Enter the threshold:')
        if ok:
            return text
        else:
            return 0.3
    
    def updateDialog(self, completed, total):
        progress = int(completed/total*100)
        self.pd.setLabelText(str(completed) +"/"+ str(total))
        self.pd.setValue(progress)
        if completed==total:
            self.onProgressDialogCanceledOrCompleted()
            
    def startOperationDialog(self):
        self.operationCanceled = False
        pd1 =  QtWidgets.QProgressDialog('Progress','Cancel',0,100,self.parent)
        pd1.setLabelText('Progress')
        pd1.setCancelButtonText('Cancel')
        pd1.setRange(0, 100)
        pd1.setValue(0)
        pd1.setMinimumDuration(0)
        pd1.show()
        pd1.canceled.connect(self.onProgressDialogCanceledOrCompleted)
        return pd1
        
        
    def onProgressDialogCanceledOrCompleted(self):
        self.operationCanceled = True
        if self.parent.lastOpenDir and osp.exists(self.parent.lastOpenDir):
            self.parent.importDirImages(self.parent.lastOpenDir)
        else:
            self.parent.loadFile(self.parent.filename)
        
    
    def saveLabelFile(self, filename, detectedShapes):
        lf = LabelFile()
        
        def format_shape(s):
            data = s.other_data.copy()
            data.update(
                dict(
                    label=s.label.encode("utf-8") if PY2 else s.label,
                    points=[(p.x(), p.y()) for p in s.points],
                    group_id=s.group_id,
                    content=s.content,
                    shape_type=s.shape_type,
                    flags=s.flags,
                )
            )
            return data

        shapes = [format_shape(item) for item in detectedShapes]
        
        imageData = LabelFile.load_image_file(filename)
        image = QtGui.QImage.fromData(imageData)
        if osp.dirname(filename) and not osp.exists(osp.dirname(filename)):
            os.makedirs(osp.dirname(filename))
        json_name = osp.splitext(filename)[0] + ".json"
        imagePath = osp.relpath(filename, osp.dirname(json_name))
        lf.save(
            filename=json_name,
            shapes=shapes,
            imagePath=imagePath,
            imageData=imageData,
            imageHeight=image.height(),
            imageWidth=image.width(),
            otherData={},
            flags={},
        )