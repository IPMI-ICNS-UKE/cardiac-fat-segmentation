#!/bin/bash
export nnUNet_raw="/home/gkolokolnikov/PhD_project/Project_EAT/cardiac-fat-segmentation/nnUNet_baseline/nnUNet_raw"
export nnUNet_preprocessed="/home/gkolokolnikov/PhD_project/Project_EAT/cardiac-fat-segmentation/nnUNet_baseline/nnUNet_preprocessed"
export nnUNet_results="/home/gkolokolnikov/PhD_project/Project_EAT/cardiac-fat-segmentation/nnUNet_baseline/nnUNet_results"

nnUNetv2_train 001 3d_fullres 0 -tr nnUNetTrainer_100epochs
nnUNetv2_train 001 3d_fullres 1 -tr nnUNetTrainer_100epochs
nnUNetv2_train 001 3d_fullres 2 -tr nnUNetTrainer_100epochs
nnUNetv2_train 001 3d_fullres 3 -tr nnUNetTrainer_100epochs
nnUNetv2_train 001 3d_fullres 4 -tr nnUNetTrainer_100epochs