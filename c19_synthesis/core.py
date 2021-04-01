# AUTOGENERATED! DO NOT EDIT! File to edit: 00_core.ipynb (unless otherwise specified).

__all__ = ['to_rgb', 'apply_dbscan_to_mask', 'grid_search_DBSCAN_params', 'label_mask_and_add_to_clusters',
           'merge_labeled_clusters', 'merge_labeled_clusters', 'get_min_max', 'pad_two_size_multiple_32',
           'correct_label_in_plot', 'get_big_lesions_labels', 'read_covid_CT_and_mask', 'normalize_rotate',
           'normalizePatches', 'plot_3d_2', 'filename', 'path_source', 'path_dest']

# Cell
def to_rgb(img, channel=1):
    '''return visible channel'''
    # rgb, a = img[:,:,:1], img[:,:,1:2]
    rgb, a = img[:,:,:channel], img[:,:,channel:channel+1]
    return 1.0-a+rgb

# Cell
def apply_dbscan_to_mask(mask, value_to_cluster=1, eps=4, min_samples=45, skip_low_intensity=2):
  '''apply dbscan to mask'''
  yy, xx  = np.where(mask==value_to_cluster)
  yy = np.expand_dims(yy,-1); xx = np.expand_dims(xx,-1);
  mm = np.concatenate((yy,xx),-1)
  clus = DBSCAN(eps=eps, min_samples=min_samples).fit(mm)
  core_samples_mask = np.zeros_like(clus.labels_, dtype=bool)
  core_samples_mask[clus.core_sample_indices_] = True
  labels = clus.labels_
  # print(np.unique(labels))
  labeled_mask = np.zeros_like(mask).astype(float)
  for i in range(len(labels)):
    labeled_mask[yy[i],xx[i]] = labels[i] + skip_low_intensity
  return labeled_mask, labels

# Cell
def grid_search_DBSCAN_params(mask_small, n_samp_min = 100, n_samp_max=150, n_samp_step=2, clus_min=3, clus_max=9):
  '''grid search on DBSCAN parameters'''
  i = 0.01
  std_small = np.inf
  eps_sel = 0
  samp_sel = 0

  for _ in tqdm(range(50)):
    for j in np.arange(n_samp_min,n_samp_max, n_samp_step):
      smaller_lesions, labels = apply_dbscan_to_mask(mask_small, eps=i, min_samples=j)
      if len(np.unique(labels)) > clus_min and len(np.unique(labels)) < clus_max:
        labs = [np.sum(labels==lab) for lab in np.unique(labels)]
        if np.max(labs) < std_small:
          std_small = np.max(labs)
          eps_sel = i
          samp_sel = j
          # print(f'{eps_sel:.1f}, {samp_sel}, {labs}, {np.std(labs):.1f}')
    i*=1.15
  return eps_sel, samp_sel

# Cell
def label_mask_and_add_to_clusters(mask, last_idx, mask_size=40):
  '''Use label function to create clusters (larger by mask_size) not identified
  by the clustering algorithm. Then put together all clusters. '''
  labeled, nr = label(mask==1)
  labels_lab = [i for i in range(nr) if np.sum(labeled == i) > mask_size]

  mm_all = np.zeros_like(mask)
  for i in np.unique(mask): # add lesions from clustering
    if i > 1:
      mm_all[np.where(mask==i)] = i
  for idx, i in enumerate(labels_lab[1:]): # add lesions from labeling
      mm_all[np.where(labeled==i)] = idx+last_idx+1
  return mm_all

# Cell
def merge_labeled_clusters(mask, DIST=40):
    '''recursive function that clusters separated masks that are close to each other.
    We merge those masks which all corners are within a distance DIST along x and y axes'''
    pairs_to_merge = []
    for idx, i in enumerate(np.unique(mask)[1:]):
        y_min, y_max, x_min, x_max, _, _ = get_min_max(np.expand_dims(mask==i,-1))
        coords_four = [[y_min,x_min], [y_min,x_max], [y_max,x_min], [y_max,x_max]]
        merge_pair = []
        merge_pair_dist = np.inf
        # get distances between the corner points of one box containing one label and all possible pairs
        for idj, j in enumerate(np.unique(mask)[1:]):
            if i!=j:
                y_min_j, y_max_j, x_min_j, x_max_j, _, _ = get_min_max(np.expand_dims(mask==j,-1))
                coords_four_j = [[y_min_j,x_min_j], [y_min_j,x_max_j], [y_max_j,x_min_j], [y_max_j,x_max_j]]
                # get distances between all corners
                y11 = np.abs(y_min-y_min_j); y12 = np.abs(y_min-y_max_j); y21 = np.abs(y_max-y_min_j); y22 = np.abs(y_max-y_max_j)
                x11 = np.abs(x_min-x_min_j); x12 = np.abs(x_min-x_max_j); x21 = np.abs(x_max-x_min_j); x22 = np.abs(x_max-x_max_j)
                y_mindist = np.min([y11,y12,y21,y22]); x_mindist = np.min([x11,x12,x21,x22])
                hyp_mindist=np.sqrt(y_mindist**2 + x_mindist**2)
                if y11 < DIST and y12 < DIST and y21 < DIST and y22 < DIST and x11 < DIST and x12 < DIST and x21 < DIST and x22 < DIST and hyp_mindist < merge_pair_dist:
                    merge_pair_dist = hyp_mindist
                    # print(f'merge {int(i),int(j)}, {hyp_mindist:.02f} {y_mindist}, {x_mindist}')
                    merge_pair = (int(i),int(j),hyp_mindist)
        pairs_to_merge.append(merge_pair)

    pairs_to_merge = list(filter(None, pairs_to_merge)) # remove empty pairs
    pairs_to_merge.sort(key=lambda tup: tup[2]) # sort pairs
    # get closest pairs of clusters (a cluster can only belong to its closest pair)
    clusters_used = []
    for i in pairs_to_merge:
        if i[0] not in clusters_used and i[1] not in clusters_used:
            clusters_used.append(i[0])
            clusters_used.append(i[1])
    # merge clusters
    unique_replaced = np.unique(mask)
    for i in range(len(clusters_used)//2):
        unique_replaced[unique_replaced==clusters_used[i*2]]= clusters_used[i*2+1]
    mask_new = np.zeros_like(mask)
    for idx, i in enumerate(np.unique(mask)[1:]):
        mask_new[np.where(mask==i)] = unique_replaced[idx+1]
    if len(pairs_to_merge)!=0: #recursive
         mask_new = merge_labeled_clusters(mask_new,DIST=DIST)
    return mask_new

# Cell
def merge_labeled_clusters(mask, DIST=40):
    '''recursive function that clusters separated masks that are close to each other.
    We merge those masks which all corners are within a distance DIST along x and y axes'''
    pairs_to_merge = []
    for idx, i in enumerate(np.unique(mask)[1:]):
        y_min, y_max, x_min, x_max, _, _ = get_min_max(np.expand_dims(mask==i,-1))
        coords_four = [[y_min,x_min], [y_min,x_max], [y_max,x_min], [y_max,x_max]]
        merge_pair = []
        merge_pair_dist = np.inf
        # get distances between the corner points of one box containing one label and all possible pairs
        for idj, j in enumerate(np.unique(mask)[1:]):
            if i!=j:
                y_min_j, y_max_j, x_min_j, x_max_j, _, _ = get_min_max(np.expand_dims(mask==j,-1))
                coords_four_j = [[y_min_j,x_min_j], [y_min_j,x_max_j], [y_max_j,x_min_j], [y_max_j,x_max_j]]
                # get distances between all corners
                y11 = np.abs(y_min-y_min_j); y12 = np.abs(y_min-y_max_j); y21 = np.abs(y_max-y_min_j); y22 = np.abs(y_max-y_max_j)
                x11 = np.abs(x_min-x_min_j); x12 = np.abs(x_min-x_max_j); x21 = np.abs(x_max-x_min_j); x22 = np.abs(x_max-x_max_j)
                y_mindist = np.min([y11,y12,y21,y22]); x_mindist = np.min([x11,x12,x21,x22])
                hyp_mindist=np.sqrt(y_mindist**2 + x_mindist**2)
                if y11 < DIST and y12 < DIST and y21 < DIST and y22 < DIST and x11 < DIST and x12 < DIST and x21 < DIST and x22 < DIST and hyp_mindist < merge_pair_dist:
                    merge_pair_dist = hyp_mindist
                    # print(f'merge {int(i),int(j)}, {hyp_mindist:.02f} {y_mindist}, {x_mindist}')
                    merge_pair = (int(i),int(j),hyp_mindist)
        pairs_to_merge.append(merge_pair)

    pairs_to_merge = list(filter(None, pairs_to_merge)) # remove empty pairs
    pairs_to_merge.sort(key=lambda tup: tup[2]) # sort pairs
    # get closest pairs of clusters (a cluster can only belong to its closest pair)
    clusters_used = []
    for i in pairs_to_merge:
        if i[0] not in clusters_used and i[1] not in clusters_used:
            clusters_used.append(i[0])
            clusters_used.append(i[1])
    # merge clusters
    unique_replaced = np.unique(mask)
    for i in range(len(clusters_used)//2):
        unique_replaced[unique_replaced==clusters_used[i*2]]= clusters_used[i*2+1]
    mask_new = np.zeros_like(mask)
    for idx, i in enumerate(np.unique(mask)[1:]):
        mask_new[np.where(mask==i)] = unique_replaced[idx+1]
    if len(pairs_to_merge)!=0: #recursive
         mask_new = merge_labeled_clusters(mask_new,DIST=DIST)
    return mask_new

# Cell
def get_min_max(mask, LABEL=1):
  yy, xx, zz = np.where(mask == LABEL)
  y_max = np.max(yy); y_min = np.min(yy)
  x_max = np.max(xx); x_min = np.min(xx)
  z_max = np.max(zz); z_min = np.min(zz)
  return y_min, y_max, x_min, x_max, z_min, z_max

# Cell
def pad_two_size_multiple_32(img, img2 = np.zeros((1)), pad_val = 16):
  '''Pad the second image with the size of the first one, or just the first one
  1. pad the second image. 2. Get the next multiple of 32
  3. Get the length to add before and after. 4. crop the padded image'''
  #1. pad first the image.
  sh_1, sh_2, sh_3 = np.shape(img)
  if (img2==False).all(): # if img2 is not used
    img_padded = np.pad(img,((pad_val,pad_val),(pad_val,pad_val),(pad_val,pad_val)))
  else:
    img_padded = np.pad(img2,((pad_val,pad_val),(pad_val,pad_val),(pad_val,pad_val)))
  #2. Get the next multiple of 32
  ch1, ch2, ch3 = np.where(img>0)
  _, _, ch1_len32 = len_multiple_32(ch1)
  _, _, ch2_len32 = len_multiple_32(ch2)
  _, _, ch3_len32 = len_multiple_32(ch3)
  #3. Get the length to add before and after
  len_to_add1 = ch1_len32 - sh_1
  len_to_add2 = ch2_len32 - sh_2
  len_to_add3 = ch3_len32 - sh_3
  add_before1, add_after1 = np.floor(len_to_add1/2), np.ceil(len_to_add1/2)
  add_before2, add_after2 = np.floor(len_to_add2/2), np.ceil(len_to_add2/2)
  add_before3, add_after3 = np.floor(len_to_add3/2), np.ceil(len_to_add3/2)
  #4. crop the padded image
  img_32 = img_padded[int(pad_val-add_before1) : int(pad_val+sh_1+add_after1),
                      int(pad_val-add_before2) : int(pad_val+sh_2+add_after2),
                      int(pad_val-add_before3) : int(pad_val+sh_3+add_after3)]
  return img_32

# Cell
def correct_label_in_plot():
    '''get a string with the network architecture to print in the figure'''
    # https://www.kite.com/python/answers/how-to-redirect-print-output-to-a-variable-in-python
    old_stdout = sys.stdout
    new_stdout = io.StringIO()
    sys.stdout = new_stdout
    print(model);
    output = new_stdout.getvalue()
    sys.stdout = old_stdout

    model_str = [i.split(', k')[0] for i in output.split('\n')]
    model_str_layers = [i.split(':')[-1] for i in model_str[2:-3]]
    model_str = [model_str[0]]+model_str_layers
    model_str = str(model_str).replace("', '",'\n')
    return model_str

# Cell
def get_big_lesions_labels(small_lesions, labels, MAX_SIZE = 40):
  masks_big = []
  for idx, i in enumerate(np.unique(labels)):
    labeled, nr = label(small_lesions==i+2)
    here = 0
    y_min, y_max, x_min, x_max, _,_ = get_min_max(np.expand_dims(small_lesions==i+2, -1))
    if idx > 1 and y_max-y_min > MAX_SIZE and x_max-x_min > MAX_SIZE:
      here = 1
      masks_big.append(i+2)
  return masks_big

# Cell
def read_covid_CT_and_mask(path_source, filename):
    filename_mask = filename.replace('_ct','_seg')
    ct = nib.load(f'{path_source}Train/volume-{filename}')
    ct_seg = np.load(f'{path_source}segmentations/segmentation-{filename}.npz')
    ct_mask = nib.load(f'{path_source}Train/volume-{filename_mask}')
    ct = np.array(ct.get_fdata())
    ct_mask = np.array(ct_mask.get_fdata())
    ct_seg = ct_seg.f.arr_0
    return ct, ct_mask, ct_seg


# Cell
def normalize_rotate(ct, ct_mask, ct_seg):
    ct = normalizePatches(ct)
    ct = np.rot90(ct)
    ct_seg = normalizePatches(ct_seg)
    ct_mask = np.rot90(ct_mask)
    ct_seg = np.swapaxes(ct_seg, 0, 1)
    ct_seg = np.swapaxes(ct_seg, 1, 2)
    return ct, ct_mask, ct_seg


# Cell
def normalizePatches(npzarray):
    '''normalize the lung region of a CT'''
    npzarray = npzarray
    maxHU = 400.
    minHU = -1000.
    npzarray = (npzarray - minHU) / (maxHU - minHU)
    npzarray[npzarray>1] = 1.
    npzarray[npzarray<0] = 0.
    return npzarray

# Cell
def plot_3d_2(image, image2, threshold=-300, detail_speed=1, detail_speed2=1, figsize=(6,6)):
    '''Plot two 3D figures together'''
    # Position the scan upright,
    # so the head of the patient would be at the top facing the camera
    p = image.transpose(1,2,0)
    p = p.transpose(1,0,2)
    p = p[:,::-1,:]

    p2 = image2.transpose(1,2,0)
    p2 = p2.transpose(1,0,2)
    p2 = p2[:,::-1,:]

    verts, faces, _, _ = measure.marching_cubes_lewiner(p, threshold, step_size=detail_speed)
    verts2, faces2, _, _ = measure.marching_cubes_lewiner(p2, threshold, step_size=detail_speed2)

    fig = plt.figure(figsize=figsize)
    ax = fig.add_subplot(111, projection='3d')

    # Fancy indexing: `verts[faces]` to generate a collection of triangles
    mesh = Poly3DCollection(verts[faces], alpha=0.3)
    face_color = [0.5, 0.5, 1]
    mesh.set_facecolor(face_color)
    ax.add_collection3d(mesh)

    # figure 2
    mesh2 = Poly3DCollection(verts2[faces2], alpha=0.3)
    face_color2 = [1, 0.5, .5]
    mesh2.set_facecolor(face_color2)
    ax.add_collection3d(mesh2)

    ax.set_xlim(0, p.shape[0])
    ax.set_ylim(0, p.shape[1])
    ax.set_zlim(0, p.shape[2])
    plt.show()

# Cell
filename = 'covid19-A-0003_ct.nii.gz'
path_source = '/content/drive/My Drive/Datasets/covid19/COVID-19-20_v2/'
path_dest = '/content/drive/My Drive/KCL/covid19/inpainting_results/'

ct, ct_mask, ct_seg = read_covid_CT_and_mask(path_source, filename)
ct, ct_mask, ct_seg = normalize_rotate(ct, ct_mask, ct_seg)
# plt.imshow(ct[...,100])
# plt.imshow(ct_mask[...,100], alpha=.3);