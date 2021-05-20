# %%
from c19_synthesis.core import *
from c19_synthesis.cellular_automata import *

import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage import label
from scipy.ndimage import binary_erosion, binary_dilation
from scipy import ndimage
import os

from skimage.segmentation import slic
from skimage.segmentation import mark_boundaries
import math
from copy import copy
from scipy.ndimage import binary_closing
from scipy.ndimage import distance_transform_bf

import torch
import torch.nn.functional as F
from time import time
from IPython.display import Image, HTML, clear_output

import imageio
import os
import moviepy.editor as mvp
from pathlib import Path
from tqdm.notebook import tqdm
import glob

# %%
data_folder = '/content/drive/MyDrive/Datasets/covid19/COVID-19-20/Train'
images = sorted(glob.glob(os.path.join(data_folder, "*_ct.nii.gz")))[:10]
labels = sorted(glob.glob(os.path.join(data_folder, "*_seg.nii.gz")))[:10]
len(images)

