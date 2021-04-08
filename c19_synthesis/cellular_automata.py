# AUTOGENERATED! DO NOT EDIT! File to edit: 01_cellular_automata.ipynb (unless otherwise specified).

__all__ = ['to_rgb', 'correct_label_in_plot', 'create_sobel_and_identity', 'ca_model_perception',
           'plot_loss_and_lesion_synthesis', 'ca_model_perception_clamp']

# Cell
import cv2
import torch
import numpy as np
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
import matplotlib.pyplot as plt
from IPython.display import Image, HTML, clear_output
import matplotlib
import io
import sys

# Cell
def to_rgb(img, channel=1):
    '''return visible channel'''
    # rgb, a = img[:,:,:1], img[:,:,1:2]
    rgb, a = img[:,:,:channel], img[:,:,channel:channel+1]
    return 1.0-a+rgb

# Cell
def correct_label_in_plot(model):
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
def create_sobel_and_identity(device='cuda'):
  ident = torch.tensor([[0.0,0.0,0.0],[0.0,1.0,0.0],[0.0,0.0,0.0]]).to(device)
  sobel_x = (torch.tensor([[-1.0,0.0,1.0],[-2.0,0.0,2.0],[-1.0,0.0,1.0]])/8.0).to(device)
  lap = (torch.tensor([[1.0,2.0,1.0],[2.0,-12,2.0],[1.0,2.0,1.0]])/16.0).to(device)
  return ident, sobel_x, lap

# Cell
class ca_model_perception(nn.Module):
    def __init__(self, checkpoint = None, seq_layers = None, device = 'cuda'):
        '''
        Kind of a modular class for a CA model
        args:
            checkpoint = 'path/to/model.pt'
            seq_layers = nn.Sequential(your, pytorch, layers)
            device = 'cuda' or 'cpu'
        '''
        super(ca_model_perception, self).__init__()

        self.ident = torch.tensor([[0.0,0.0,0.0],[0.0,1.0,0.0],[0.0,0.0,0.0]]).to(device)
        self.sobel_x = (torch.tensor([[-1.0,0.0,1.0],[-2.0,0.0,2.0],[-1.0,0.0,1.0]])/8.0).to(device)
        self.lap = (torch.tensor([[1.0,2.0,1.0],[2.0,-12,2.0],[1.0,2.0,1.0]])/16.0).to(device)

        if seq_layers is not None:
            self.model = seq_layers
        else:
            self.model = nn.Sequential(
                nn.Conv2d(64, 256, kernel_size = 3,padding =1,  bias = True),
                nn.ReLU(),
                nn.Conv2d(256, 256, kernel_size = 3,padding =1,  bias = True),
                nn.ReLU(),
                nn.Conv2d(256, 16, kernel_size =  1, bias = True),
            )

        '''
        initial condition for "do nothing" behaviour:
            * all biases should be zero
            * the weights of the last layer should be zero
        '''
        for l in range(len(self.model)):
            if isinstance(self.model[l], nn.Conv2d):
                self.model[l].bias.data.fill_(0)
                if l == len(self.model) -1:
                    self.model[l].weight.data.fill_(0)

        if checkpoint is not None:
            self.load_state_dict(torch.load(checkpoint))

        self.to(device= device)

    def perchannel_conv(self, x, filters):
        '''filters: [filter_n, h, w]'''
        b, ch, h, w = x.shape
        y = x.reshape(b*ch, 1, h, w)
        y = torch.nn.functional.pad(y, [1, 1, 1, 1], 'circular')
        y = torch.nn.functional.conv2d(y, filters[:,None])
        return y.reshape(b, -1, h, w)

    def perception(self, x):
        filters = torch.stack([self.ident, self.sobel_x, self.sobel_x.T, self.lap])
        return self.perchannel_conv(x, filters)

    def normalize_grads(self):
        '''
        gradient normalization for constant step size and to avoid spikes
        '''
        for p in self.parameters():
            p.grad.data = p.grad.data/(p.grad.data.norm()+1e-8)


    def get_alive_mask(self, x):
        '''
        looks for cells that have values over 0.1,
        and allows only their adjacent cells to participate in growth
        '''
        alpha = x[:,1:2,:,:]
        pooled = (F.max_pool2d(alpha, 3,1, padding =1 ) > 0.1).float()
        return pooled

    def train_step(self, seed, target, target_loss_func, iters, current_epoch = 1000, masked_loss=False):
        '''
        a single training step for the model,
        feel free to play around with different loss functions like L1 loss

        the loss is calculated for only the first 4 channels of the output
        '''
        x = seed
        for i in range(iters):
            x, alive_mask =  self.forward(x,i, current_epoch)

        # print(x[:,:4, :,:].shape, target.shape)
        # batch_mean_rmse_per_pixel = torch.mean(torch.sqrt((x[:,:1, :,:] - target)**2),dim=0)
        batch_mean_rmse_per_pixel = torch.mean(torch.sqrt((x[:,0, :,:] - target[:,0,:,:])**2),dim=0)

        if masked_loss == True:
            alive_mask_dilated = (F.max_pool2d(alive_mask[0], 3,1, padding =1 ) > 0.1).float()
            # alive_mask_dilated = torch.from_numpy(binary_closing(alive_mask[0].cpu().numpy() > 0.1)).float().to('cuda')
            target_loss  =  target_loss_func(x[:,:1, :,:] * alive_mask_dilated, target * alive_mask_dilated)
        else:
            target_loss  =  target_loss_func(x[:,:2, :,:] * target[:,1:,...], target * target[:,1:,...]) # used to synthesize almost all nodules



        loss = target_loss

        return loss, x, alive_mask.cpu().numpy() #batch_mean_rmse_per_pixel.detach().cpu().numpy()

    def forward(self, x, i, current_epoch):
        '''
        nice little forward function for the model
        1. fetches an alive mask
        2. generates another random mask of 0's and 1's
        3. updates the input
        4. applies alive mask
        '''
        if current_epoch < 100:
          alive_mask = self.get_alive_mask(x)
        else:
          if i % 3 == 0:
            alive_mask = self.get_alive_mask(x)
          else:
            # alive_mask = self.get_alive_mask(x)
            alive_mask = (x[:,1:2,:,:] > 0.1).float()
        mask = torch.clamp(torch.round(torch.rand_like(x[:,:1,:,:])) , 0,1)
        y = self.perception(x)
        out = x + self.model(y)*mask
        out *= alive_mask

        return out, alive_mask

# Cell
def plot_loss_and_lesion_synthesis(losses, optimizer, model_str, i, loss, sample_size, out):
  clear_output(True)
  f, (ax0, ax1) = plt.subplots(2, 1, figsize=(12,10), gridspec_kw={'height_ratios': [4, 1]})
  lr_info = f'\nlr_init={optimizer.param_groups[0]["initial_lr"]:.1E}\nlr_last={optimizer.param_groups[0]["lr"]:.1E}'
  model_str_final = model_str+lr_info
  ax0.plot(losses, label=model_str_final)
  ax0.set_yscale('log')
  ax0.legend(loc='upper right', fontsize=16)

  stack = []
  for z in range(sample_size):
      stack.append(to_rgb(out[z].permute(-2, -1,0).cpu().detach().numpy()))
  ax1.imshow(np.clip(np.hstack(np.squeeze(stack)), 0,1))
  ax1.axis('off')
  plt.show()
  print(i, loss.item(), flush = True)
  return model_str_final

# Cell
class ca_model_perception_clamp(nn.Module):
    def __init__(self, checkpoint = None, seq_layers = None, device = 'cuda'):
        '''
        Kind of a modular class for a CA model
        args:
            checkpoint = 'path/to/model.pt'
            seq_layers = nn.Sequential(your, pytorch, layers)
            device = 'cuda' or 'cpu'
        '''
        super(ca_model_perception_clamp, self).__init__()

        self.ident = torch.tensor([[0.0,0.0,0.0],[0.0,1.0,0.0],[0.0,0.0,0.0]]).to(device)
        self.sobel_x = (torch.tensor([[-1.0,0.0,1.0],[-2.0,0.0,2.0],[-1.0,0.0,1.0]])/8.0).to(device)
        self.lap = (torch.tensor([[1.0,2.0,1.0],[2.0,-12,2.0],[1.0,2.0,1.0]])/16.0).to(device)

        if seq_layers is not None:
            self.model = seq_layers
        else:
            self.model = nn.Sequential(
                nn.Conv2d(64, 256, kernel_size = 3,padding =1,  bias = True),
                nn.ReLU(),
                nn.Conv2d(256, 256, kernel_size = 3,padding =1,  bias = True),
                nn.ReLU(),
                nn.Conv2d(256, 16, kernel_size =  1, bias = True),
            )

        '''
        initial condition for "do nothing" behaviour:
            * all biases should be zero
            * the weights of the last layer should be zero
        '''
        for l in range(len(self.model)):
            if isinstance(self.model[l], nn.Conv2d):
                self.model[l].bias.data.fill_(0)
                if l == len(self.model) -1:
                    self.model[l].weight.data.fill_(0)

        if checkpoint is not None:
            self.load_state_dict(torch.load(checkpoint))

        self.to(device= device)

    def perchannel_conv(self, x, filters):
        '''filters: [filter_n, h, w]'''
        b, ch, h, w = x.shape
        y = x.reshape(b*ch, 1, h, w)
        y = torch.nn.functional.pad(y, [1, 1, 1, 1], 'circular')
        y = torch.nn.functional.conv2d(y, filters[:,None])
        return y.reshape(b, -1, h, w)

    def perception(self, x):
        filters = torch.stack([self.ident, self.sobel_x, self.sobel_x.T, self.lap])
        return self.perchannel_conv(x, filters)

    def normalize_grads(self):
        '''
        gradient normalization for constant step size and to avoid spikes
        '''
        for p in self.parameters():
            p.grad.data = p.grad.data/(p.grad.data.norm()+1e-8)


    def get_alive_mask(self, x):
        '''
        looks for cells that have values over 0.1,
        and allows only their adjacent cells to participate in growth
        '''
        alpha = x[:,1:2,:,:]
        pooled = (F.max_pool2d(alpha, 3,1, padding =1 ) > 0.1).float()
        return pooled

    def train_step(self, seed, target, target_loss_func, iters, current_epoch = 1000, masked_loss=False):
        '''
        a single training step for the model,
        feel free to play around with different loss functions like L1 loss

        the loss is calculated for only the first 4 channels of the output
        '''
        x = seed
        for i in range(iters):
            x, alive_mask, mask_diff =  self.forward(x,i, current_epoch)

        # print(x[:,:4, :,:].shape, target.shape)
        # batch_mean_rmse_per_pixel = torch.mean(torch.sqrt((x[:,:1, :,:] - target)**2),dim=0)
        batch_mean_rmse_per_pixel = torch.mean(torch.sqrt((x[:,0, :,:] - target[:,0,:,:])**2),dim=0)

        if masked_loss == True:
            alive_mask_dilated = (F.max_pool2d(alive_mask[0], 3,1, padding =1 ) > 0.1).float()
            # alive_mask_dilated = torch.from_numpy(binary_closing(alive_mask[0].cpu().numpy() > 0.1)).float().to('cuda')
            target_loss  =  target_loss_func(x[:,:1, :,:] * alive_mask_dilated, target * alive_mask_dilated)
        else:
            target_loss  =  target_loss_func(x[:,:2, :,:] * target[:,1:,...], target * target[:,1:,...]) # used to synthesize almost all nodules



        loss = target_loss

        return loss, x, alive_mask.cpu().numpy(), mask_diff.cpu().numpy() #batch_mean_rmse_per_pixel.detach().cpu().numpy()

    def forward(self, x, i, current_epoch):
        '''
        nice little forward function for the model
        1. fetches an alive mask
        2. generates another random mask of 0's and 1's
        3. updates the input
        4. applies alive mask
        '''
        mask_previous = alive_mask = (x[:,1:2,:,:] > 0.1).float()
        if current_epoch < 100:
          alive_mask = self.get_alive_mask(x)
        else:
          if i % 3 == 0:
            alive_mask = self.get_alive_mask(x)
          else:
            # alive_mask = self.get_alive_mask(x)
            alive_mask = (x[:,1:2,:,:] > 0.1).float()
        mask_diff = alive_mask - mask_previous
        mask = torch.clamp(torch.round(torch.rand_like(x[:,:1,:,:])) , 0,1)
        y = self.perception(x)
        mask_new_cells_clamped = torch.clip((1-mask_diff)+.19,0,1) #make sure this is only applied to the first channel

        mask_new_cells_clamped_ones = torch.ones_like(torch.squeeze(mask_new_cells_clamped))
        mask_new_cells_clamped2 = torch.repeat_interleave(mask_new_cells_clamped,16,1)
        for i in np.arange(1,16,1):
          mask_new_cells_clamped2[:,i,:,:] = mask_new_cells_clamped_ones

        out = x + self.model(y)*mask*mask_new_cells_clamped2
        out *= alive_mask

        return out, alive_mask, mask_diff