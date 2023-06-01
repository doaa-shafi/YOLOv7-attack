import argparse
import time
from pathlib import Path

import cv2
import torch
import torchvision
import torchvision.transforms as T
from PIL import Image
import torch.backends.cudnn as cudnn
from numpy import random
import numpy as np
import math
import torch.nn.functional as F
from models.experimental import attempt_load
from utils.datasets import LoadStreams, LoadImages
from utils.general import check_img_size, check_requirements, check_imshow, non_max_suppression, apply_classifier, \
    scale_coords, xyxy2xywh, strip_optimizer, set_logging, increment_path
from utils.plots import plot_one_box
from utils.torch_utils import select_device, load_classifier, time_synchronized, TracedModel
from torch.cuda import amp

img=0
mask=0
need=0
images=[]
fps=0
def detect(save_img=False):
    global img
    global mask
    global need
    global images
    global fps
    source, weights, view_img, save_txt, imgsz, trace = opt.source, opt.weights, opt.view_img, opt.save_txt, opt.img_size, not opt.no_trace
    save_img = not opt.nosave and not source.endswith('.txt')  # save inference images
    webcam = source.isnumeric() or source.endswith('.txt') or source.lower().startswith(
        ('rtsp://', 'rtmp://', 'http://', 'https://'))

    # Directories
    save_dir = Path(increment_path(Path(opt.project) / opt.name, exist_ok=opt.exist_ok))  # increment run
    (save_dir / 'labels' if save_txt else save_dir).mkdir(parents=True, exist_ok=True)  # make dir

    # Initialize
    set_logging()
    device = select_device(opt.device)
    half = device.type != 'cpu'  # half precision only supported on CUDA

    # Load model
    model = attempt_load(weights, map_location=device)  # load FP32 model
    stride = int(model.stride.max())  # model stride
    imgsz = check_img_size(imgsz, s=stride)  # check img_size
    trace=False
    if trace:
        model = TracedModel(model, device, opt.img_size)

    if half:
        model.half()  # to FP16

    # Second-stage classifier
    classify = False
    if classify:
        modelc = load_classifier(name='resnet101', n=2)  # initialize
        modelc.load_state_dict(torch.load('weights/resnet101.pt', map_location=device)['model']).to(device).eval()

    # Set Dataloader
    vid_path, vid_writer = None, None
    if webcam:
        view_img = check_imshow()
        cudnn.benchmark = True  # set True to speed up constant image size inference
        dataset = LoadStreams(source, img_size=imgsz, stride=stride)
    else:
        dataset = LoadImages(source, img_size=imgsz, stride=stride)

    # Get names and colors
    names = model.module.names if hasattr(model, 'module') else model.names
    colors = [[random.randint(0, 255) for _ in range(3)] for _ in names]

    # Run inference
    if device.type != 'cpu':
        model(torch.zeros(1, 3, imgsz, imgsz).to(device).type_as(next(model.parameters())))  # run once
    old_img_w = old_img_h = imgsz
    old_img_b = 1

    t0 = time.time()
    frame_n=0
    for path, img, im0s, vid_cap in dataset:
        img=np.transpose(img,(1,2,0))
        img=cv2.resize(img,(640,448))
        img=np.transpose(img,(2,0,1))
        img = torch.from_numpy(img).to(device)
        img = img.half() if half else img.float()  # uint8 to fp16/32
        img /= 255.0  # 0 - 255 to 0.0 - 1.0
        if img.ndimension() == 3:
            img = img.unsqueeze(0)
        img.requires_grad = True
        # Warmup
        # if device.type != 'cpu' and (old_img_b != img.shape[0] or old_img_h != img.shape[2] or old_img_w != img.shape[3]):
        #     old_img_b = img.shape[0]
        #     old_img_h = img.shape[2]
        #     old_img_w = img.shape[3]
        #     for i in range(3):
        #         model(img, augment=opt.augment)[0]

        # Inference
        t1 = time_synchronized()
        # with torch.no_grad():   # Calculating gradients would cause a GPU memory leak
        output1= model(img, augment=opt.augment)[1]
        pred = model(img, augment=opt.augment)[0]
       
        
            
        t2 = time_synchronized()

        # Apply NMS
        pred,need = non_max_suppression(pred, opt.conf_thres, opt.iou_thres, classes=opt.classes, agnostic=opt.agnostic_nms)
        output2=pred
        mask=[]
        for i,f in enumerate(output2[0]):
            if int(f[2].item())-int(f[0].item())<40 or int(f[3].item())-int(f[1].item())<40:
                mask.append((0,0))
            else:
                mask.append((int(f[0].item()),int(f[1].item()),int(f[2].item()),int(f[3].item())))   
        r=0
        perturbed_image=img.clone().detach()
        for i in range(1):
            for a,b in enumerate(need):
                if len(mask[a])!=2:
                    img.grad=None
                    b[0][int(b[1])+5].backward(retain_graph=True)
                    tmp=b[0].clone().detach()
                    tmp[0]=0
                    tmp[1]=0
                    tmp[2]=0
                    tmp[3]=0
                    tmp[4]=0
                    top2,top2in=torch.topk(tmp,10)
                    print(top2)
                    print(top2in)
                    data_grad1=img.grad.data
                    img.grad=None
                    b[0][top2in[1]].backward(retain_graph=True)
                    data_grad2=img.grad.data
                    img.grad=None
                    b[0][top2in[2]].backward(retain_graph=True)
                    data_grad3=img.grad.data
                    factor=1
                    if i==1:
                        factor=int((b[0][top2in[0]]/b[0][top2in[1]]).item())
                        factor=math.log(factor,10)
                        factor = round(factor, 0)
                        factor=10**factor
                    print(factor)
                    r=factor*data_grad2-data_grad1
                    if len(need)!=1:
                        # for a1,a2 in enumerate(r):
                        #     for a3,a4 in enumerate(a2):
                        #         for a5,a6 in enumerate(a4):
                        #             for a7,a28 in enumerate(a6):
                        #                 if a7<mask[a][0] or a7>mask[a][2] or a5<mask[a][1] or a5>mask[a][3]:
                        #                     r[a1][a3][a5][a7]=0
                        r[0][0][:,0:mask[a][0]]=0
                        r[0][0][0:mask[a][1],:]=0
                        r[0][0][:,mask[a][2]+1:]=0
                        r[0][0][mask[a][3]+1:,:]=0
                        r[0][1][:,0:mask[a][0]]=0
                        r[0][1][0:mask[a][1],:]=0
                        r[0][1][:,mask[a][2]+1:]=0
                        r[0][1][mask[a][3]+1:,:]=0
                        r[0][2][:,0:mask[a][0]]=0
                        r[0][2][0:mask[a][1],:]=0
                        r[0][2][:,mask[a][2]+1:]=0
                        r[0][2][mask[a][3]+1:,:]=0

                    # if i==0:
                    #     vis=r.squeeze()
                    #     transform = T.ToPILImage()
                    #     new = transform(vis)
                    #     new.save('perturbation.jpg')
                    perturbed_image=fgsm_attack(perturbed_image,0.05,r)
                    
        vis=perturbed_image.squeeze()
        # new=vis.cpu().numpy()
        # new=np.transpose(new,(1,2,0))
        transform = T.ToPILImage()
        new = transform(vis)
        new.save('result_'+str(frame_n+1)+'.jpg')
        images.append('result_'+str(frame_n+1)+'.jpg')
        t3 = time_synchronized()

        # Apply Classifier
        if classify:
            pred = apply_classifier(pred, modelc, img, im0s)
        
        # Process detections
        for i, det in enumerate(pred):  # detections per image
            if webcam:  # batch_size >= 1
                p, s, im0, frame = path[i], '%g: ' % i, im0s[i].copy(), dataset.count
            else:
                p, s, im0, frame = path, '', im0s, getattr(dataset, 'frame', 0)

            p = Path(p)  # to Path
            save_path = str(save_dir / p.name)  # img.jpg
            txt_path = str(save_dir / 'labels' / p.stem) + ('' if dataset.mode == 'image' else f'_{frame}')  # img.txt
            gn = torch.tensor(im0.shape)[[1, 0, 1, 0]]  # normalization gain whwh
            
            if len(det):
                # Rescale boxes from img_size to im0 size
                det[:, :4] = scale_coords(img.shape[2:], det[:, :4], im0.shape).round()
                # Print results
                for c in det[:, -1].unique():
                    n = (det[:, -1] == c).sum()  # detections per class
                    s += f"{n} {names[int(c)]}{'s' * (n > 1)}, "  # add to string
                # Write results
                for *xyxy, conf, cls in reversed(det):
                    if save_txt:  # Write to file
                        xywh = (xyxy2xywh(torch.tensor(xyxy).view(1, 4)) / gn).view(-1).tolist()  # normalized xywh
                        line = (cls, *xywh, conf) if opt.save_conf else (cls, *xywh)  # label format
                        with open(txt_path + '.txt', 'a') as f:
                            f.write(('%g ' * len(line)).rstrip() % line + '\n')

                    if save_img or view_img:  # Add bbox to image
                        label = f'{names[int(cls)]} {conf:.2f}'
                        plot_one_box(xyxy, im0, label=label, color=colors[int(cls)], line_thickness=1)
            # Print time (inference + NMS)
            print(f'{s}Done. ({(1E3 * (t2 - t1)):.1f}ms) Inference, ({(1E3 * (t3 - t2)):.1f}ms) NMS')
        
            # Stream results
            if view_img:
                cv2.imshow(str(p), im0)
                cv2.waitKey(1)  # 1 millisecond
            # Save results (image with detections)
            if save_img:
                if dataset.mode == 'image':
                    cv2.imwrite(save_path, im0)
                    print(f" The image with the result is saved in: {save_path}")
                else:  # 'video' or 'stream'
                    if vid_path != save_path:  # new video
                        vid_path = save_path
                        if isinstance(vid_writer, cv2.VideoWriter):
                            vid_writer.release()  # release previous video writer
                        if vid_cap:  # video
                            fps = vid_cap.get(cv2.CAP_PROP_FPS)
                            w = int(vid_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                            h = int(vid_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        else:  # stream
                            fps, w, h = 30, im0.shape[1], im0.shape[0]
                            save_path += '.mp4'
                        vid_writer = cv2.VideoWriter(save_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (w, h))
                    vid_writer.write(im0)
        frame_n+=1
    
    if save_txt or save_img:
        s = f"\n{len(list(save_dir.glob('labels/*.txt')))} labels saved to {save_dir / 'labels'}" if save_txt else ''
        #print(f"Results saved to {save_dir}{s}")
    print(f'Done. ({time.time() - t0:.3f}s)')


def fgsm_attack(image, epsilon, data_grad):
    # Collect the element-wise sign of the data gradient
    sign_data_grad = data_grad.sign()
    # Create the perturbed image by adjusting each pixel of the input image
    perturbed_image = image+epsilon*sign_data_grad
    # Adding clipping to maintain [0,1] range
    perturbed_image = torch.clamp(perturbed_image, 0, 1)
    # Return the perturbed image
    return perturbed_image

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--weights', nargs='+', type=str, default='yolov7.pt', help='model.pt path(s)')
    parser.add_argument('--source', type=str, default='inference/images', help='source')  # file/folder, 0 for webcam
    parser.add_argument('--img-size', type=int, default=640, help='inference size (pixels)')
    parser.add_argument('--conf-thres', type=float, default=0.25, help='object confidence threshold')
    parser.add_argument('--iou-thres', type=float, default=0.45, help='IOU threshold for NMS')
    parser.add_argument('--device', default='', help='cuda device, i.e. 0 or 0,1,2,3 or cpu')
    parser.add_argument('--view-img', action='store_true', help='display results')
    parser.add_argument('--save-txt', action='store_true', help='save results to *.txt')
    parser.add_argument('--save-conf', action='store_true', help='save confidences in --save-txt labels')
    parser.add_argument('--nosave', action='store_true', help='do not save images/videos')
    parser.add_argument('--classes', nargs='+', type=int, help='filter by class: --class 0, or --class 0 2 3')
    parser.add_argument('--agnostic-nms', action='store_true', help='class-agnostic NMS')
    parser.add_argument('--augment', action='store_true', help='augmented inference')
    parser.add_argument('--update', action='store_true', help='update all models')
    parser.add_argument('--project', default='runs/detect', help='save results to project/name')
    parser.add_argument('--name', default='exp', help='save results to project/name')
    parser.add_argument('--exist-ok', action='store_true', help='existing project/name ok, do not increment')
    parser.add_argument('--no-trace', action='store_true', help='don`t trace model')
    opt = parser.parse_args()
    cuda = True
    print(opt)

    if opt.update:  # update all models (to fix SourceChangeWarning)
        for opt.weights in ['yolov7.pt']:
            detect()
            strip_optimizer(opt.weights)
    else:
        detect()

     
    img_array = []
    for filename in images:
        img = cv2.imread(str(filename))
        print(filename)
        print(str(filename))
        height, width, layers = img.shape
        size = (width,height)
        img_array.append(img)
    
    
    out = cv2.VideoWriter('project.avi',cv2.VideoWriter_fourcc(*'DIVX'), fps, size)
    
    for i in range(len(img_array)):
        out.write(img_array[i])
    out.release()
    
    
        



   