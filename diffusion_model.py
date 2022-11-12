import torch
from torch import nn
import numpy as np
import math

class Block(nn.Module):
    def __init__(self,in_channels, out_channels, time_emb_dim):
        super(Block, self).__init__()
        self.time =  nn.Linear(time_emb_dim, out_channels)
        self.conv1 = nn.Conv2d(in_channels, out_channels, kernel_size=3, stride=1, padding=1)
        self.shortcut = nn.Sequential()

        self.conv2 = nn.Conv2d(out_channels, out_channels, kernel_size=3, stride=1, padding=1)
        self.bn1 = nn.BatchNorm2d(out_channels)
        self.bn2 = nn.BatchNorm2d(out_channels)

    def forward(self, x, timestep_embedding):
        shortcut = self.shortcut(x)
        t = nn.Relu()(self.time(timestep_embedding))[(..., ) + (None, ) * 2] # Needs to be worked on.
        x = nn.ReLU()(self.bn1(self.conv1(x)))
        x = x + t
        x = nn.ReLU()(self.bn2(self.conv2(x)))
        x = x + shortcut
        return nn.ReLU()(x)

class downStep(nn.Module):
  def __init__(self, in_channels, out_channels, timestep_embedding):
    super(downStep, self).__init__()
    #todo
    self.maxp = nn.Sequential(nn.MaxPool2d(2),
        Block(in_channels, out_channels, timestep_embedding)
        )

  def forward(self, x, timestep_embedding):
    #todo
    down1 = self.maxp(x, timestep_embedding)
    # t = self.relu(self.time(timestep_embedding))
    # down1 = down1 + t
    return down1


class upStep(nn.Module):
  def __init__(self, in_channels, out_channels, timestep_embedding):
    super(upStep, self).__init__()
    #todo
    self.expanding = nn.ConvTranspose2d(in_channels, out_channels, kernel_size=2,stride = 2)#Upsample(scale_factor = 2, mode='bilinear'
    self.c = Block(in_channels, out_channels, timestep_embedding)

  def forward(self, x, y, timestep_embedding):
    #todo
    x1 = self.expanding(x)
    crop_x = (y.size()[2] - x1.size()[2]) // 2
    crop_y = (y.size()[3] - x1.size()[3]) // 2

    y = y[:,:,crop_x:y.size()[2] - crop_x,crop_y:y.size()[3] - crop_y] # 12: 48, 12:48

    blk = torch.cat([y,x1], dim=1)
    output = self.c(blk, timestep_embedding)
    #t = self.relu(self.time(timestep_embedding))
    #output = output + t
    return output

# class Sine_Cosine_Embedding(nn.Module):
#     def __init__(self, dim):
#         super(Sine_Cosine_Embedding, self).__init__()
#         self.dim = dim
#         self.n = 10000
    
#     def forward(self, timesteps):
#         # Expecting timesteps as [[0],[1],[2],[3],[4],....,[T]]
#         i = (timesteps)
#         denominator = self.n**((2*i)//self.dim)
#         timesteps = torch.tensor(timesteps/denominator)
#         return torch.hstack((torch.sin(timesteps), torch.cos(timesteps)))

class SinusoidalPositionEmbeddings(nn.Module):
    def __init__(self, dim):
        super(SinusoidalPositionEmbeddings, self).__init__()
        self.dim = dim

    def forward(self, time):
        device = torch.device('cpu') # changed from time.device to cpu
        half_dim = self.dim // 2
        embeddings = math.log(10000) / (half_dim - 1)
        embeddings = torch.exp(torch.arange(half_dim, device=device) * -embeddings)
        embeddings = time[:, None] * embeddings[None, :]
        embeddings = torch.cat((embeddings.sin(), embeddings.cos()), dim=-1)
        # TODO: Double check the ordering here
        return embeddings
        
class Diffusion_model(nn.Module):
    def __init__(self, beta_start, beta_end, timesteps):
        super(Diffusion_model, self).__init__()
        self.beta_start = beta_start
        self.beta_end = beta_end
        self.timesteps = timesteps
        self.beta_schedule = self.linearBetaSchedule()
        self.alpha = self.alphaGeneration()
        self.alpha_bar = self.alphaBar()    
        self.sqrt_alpha_bar = torch.sqrt(self.alpha_bar)
        self.sqrt_one_minus_alpha_bar = torch.sqrt(1.0-self.alpha_bar)

        timestep_embedding = 32
        self.time = nn.Sequential(
            #Sine_Cosine_Embedding(timestep_embedding),
            SinusoidalPositionEmbeddings(timestep_embedding),
            nn.Linear(timestep_embedding, timestep_embedding),
            nn.ReLU()
        )
        self.c1 = Block(1,64, 32)
        self.d1 = downStep(64, 128, timestep_embedding)
        self.d2 = downStep(128, 256, timestep_embedding)
        self.d3 = downStep(256, 512, timestep_embedding)
        self.d4 = downStep(512,1024, timestep_embedding)
        self.u1 = upStep(1024, 512, timestep_embedding)
        self.u2 = upStep(512, 256, timestep_embedding)
        self.u3 = upStep(256, 128, timestep_embedding)
        self.u4 = upStep(128, 64, timestep_embedding)
        self.c2 = nn.Conv2d(64, 3, kernel_size=1)

    def alphaGeneration(self):
        return 1.0-self.beta_schedule

    def linearBetaSchedule(self):
        return torch.linspace(self.beta_start, self.beta_end, self.timesteps)

    def alphaBar(self):
        return torch.cumprod(self.alpha, dim=0)

    def forwardNoise(self, x, t):
        noise = torch.randn_like(x.float())
        alpha_root_bar =  torch.reshape(self.sqrt_alpha_bar[t], (-1, 1, 1, 1))
        one_min_alpha_root_bar = torch.reshape(self.sqrt_one_minus_alpha_bar[t], (-1, 1, 1, 1))
        noisy_image = ( alpha_root_bar * x ) + one_min_alpha_root_bar * noise
        return noisy_image, noise

    def forward(self, x, timestep_embedding=32):
        t = self.time(timestep_embedding)
        y = self.c1(x, t)
        
        l1 = self.d1(y, t)
        
        l2 = self.d2(l1, t)
        
        l3 = self.d3(l2, t)
        
        l4 = self.d4(l3, t)
        
        l6 = self.u1(l4, l3, t)
        
        l7 = self.u2(l6, l2, t)
        
        l8 = self.u3(l7, l1, t)
        
        l9 = self.u4(l8, y, t)
        
        out = self.c2(l9)

        return out

    def predict(self, batch):
        noisedBatch = self.forwardNoise(batch, self.timesteps)
        for timestep in reversed(self.timesteps):
            noisedBatch = noisedBatch - self.forward(noisedBatch, timestep)
        coloredBatch = noisedBatch
        return coloredBatch

