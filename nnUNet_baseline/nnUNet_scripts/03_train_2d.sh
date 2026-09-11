#!/bin/bash
export nnUNet_raw="/home/gkolokolnikov/PhD_project/Project_EAT/cardiac-fat-segmentation/nnUNet_baseline/nnUNet_raw"
export nnUNet_preprocessed="/home/gkolokolnikov/PhD_project/Project_EAT/cardiac-fat-segmentation/nnUNet_baseline/nnUNet_preprocessed"
export nnUNet_results="/home/gkolokolnikov/PhD_project/Project_EAT/cardiac-fat-segmentation/nnUNet_baseline/nnUNet_results"

nnUNetv2_train 001 2d 0