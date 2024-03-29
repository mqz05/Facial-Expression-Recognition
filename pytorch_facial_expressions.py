
import csv
import os
from PIL import Image
import torch
from torch import nn
import numpy as np
from torch.utils.data import Dataset, DataLoader
import face_recognition
from pathlib import Path


MAIN_PATH = "/Users/muqi/Desktop/Python/PyTorch/Datasets/facial_expressions_2/facial_expressions_dataset/"

def getLabelValue(label: str):
    match label:
        case "surprise":
            return 0
        case "happy":
            return 1
        case "neutral":
            return 2
        case "contempt":
            return 3
        case "disgust":
            return 4
        case "fear":
            return 5
        case "sad":
            return 6
        case "anger":
            return 7
        case _:
            print("Wrong Label Detected")
            return -1



class MLP(nn.Module):
    def __init__(self, num_layers, in_dim, hidden_dim, out_dim):
        super().__init__()
        self.num_layers = num_layers
        self.in_dim = in_dim
        self.hidden_dim = hidden_dim
        self.out_dim = out_dim
        self.activation = nn.ReLU()     # Using ReLu
    
        """
        nonlin = True
        if self.activation is None:
            nonlin = False
        """

        layers = []
        for i in range(num_layers - 1):
            layers.extend(
                self._layer(
                    hidden_dim if i > 0 else in_dim,
                    hidden_dim,
                    True,  # nonlin,
                )
            )
        layers.extend(self._layer(hidden_dim, out_dim, False))

        self.model = nn.Sequential(*layers)

    def _layer(self, in_dim, out_dim, activation=True):
        if activation:
            return [
                nn.Linear(in_dim, out_dim),
                self.activation,
            ]
        else:
            return [
                nn.Linear(in_dim, out_dim),
            ]

    def forward(self, x):
        out = self.model(x.float())
        return out



def _create_npy_files(path = MAIN_PATH + 'labels.csv'):
    X_path = path[:-4] + '.X.npy'
    Y_path = path[:-4] + '.Y.npy'

    csv_file = open(path, 'r')
    reader = csv.reader(csv_file)

    # Discard header
    row = next(reader)

    y_list = []
    X_list = []
    counter = 0
    skip_counter = 0


    for i, row in enumerate(reader):
        counter +=1

        # Set label value
        y_str = row[2]
        y = getLabelValue(y_str)

        image = Image.open(MAIN_PATH + row[1])
        
        face_bounding_borders = face_recognition.api.face_locations(np.asarray(image))

        # Rearrange borders (top, botom, lef, right are messed up) and crop image
        if face_bounding_borders != []:
            image = image.crop((face_bounding_borders[0][3], face_bounding_borders[0][0], face_bounding_borders[0][1], face_bounding_borders[0][2]))
            image = image.resize((96, 96))

        face_landmarks_list = face_recognition.face_landmarks(np.asarray(image))

        landmarks_array = []
        for face_landmarks in face_landmarks_list:
            for facial_feature in face_landmarks.keys():
                for item in face_landmarks[facial_feature]:
                    # Ideally we would separate depending on each facial feature (so the shape afterwards have more dimensions/parametres)
                    landmarks_array.append(np.round(item[0] / 96, 5))
                    landmarks_array.append(np.round(item[1] / 96, 5))

        if face_landmarks_list and len(landmarks_array) == 144:
            X_list.append(landmarks_array)
            y_list.append(y)
        else:
            skip_counter +=1
        
    X = np.asarray(X_list)
    y = np.asarray(y_list)
    np.save(X_path, X)
    np.save(Y_path, y)
    print(skip_counter,'missed, out of', counter, ' - total:', (counter - skip_counter) / counter, '%')
    

def _load_data(x_path: str, expect_labels = True):

    # If a previous call to this method has already converted
    # the data to numpy format, load the numpy directly
    X_path = MAIN_PATH + x_path
    Y_path = MAIN_PATH + "labels.Y.npy"
    
    if os.path.exists(X_path):
        X = np.load(X_path, allow_pickle=True)

        if expect_labels:
            y = np.load(Y_path, allow_pickle=True)
        else:
            y = None
        return X, y
    else:
        print("Something went wrong, path not found, should we reevaluate landmarks?")
        return
        

X, y = _load_data("original_labels.X.npy")


NUM_TRAINING_IMAGES = int(len(X) * 0.8)


class PrepareData(Dataset):
    def __init__(self, x, y):
        self.x = torch.from_numpy(x) if not torch.is_tensor(x) else x
        self.y = torch.from_numpy(y) if not torch.is_tensor(y) else y

    def __len__(self):
        return len(self.x)

    def __getitem__(self, idx):
        return self.x[idx], self.y[idx]


trainer_loader = PrepareData(x=X[:NUM_TRAINING_IMAGES], y=y[:NUM_TRAINING_IMAGES])
test_loader = PrepareData(x=X[NUM_TRAINING_IMAGES:], y=y[NUM_TRAINING_IMAGES:])
print(trainer_loader[1][0].shape)
print(test_loader[1])


# Hyper Parameters
EPOCH = 500
BATCH_SIZE = 16
LR = 0.0001

# Data Loader for easy mini-batch return in training
train_loader = DataLoader(trainer_loader, batch_size=BATCH_SIZE, shuffle=True)
test_loader = DataLoader(test_loader, batch_size=1, shuffle=False)



model = MLP(num_layers=5, in_dim=144, hidden_dim=256, out_dim=8)
print(model)

optimizer = torch.optim.Adam(model.parameters(), lr=LR)
# optimizer = torch.optim.SGD(model.parameters(), lr=LR, momentum=0.7)
loss_func = nn.CrossEntropyLoss()
average_loss = 2
correct_ratio = 0


for epoch in range(EPOCH):
    
    for step, (b_x, b_y) in enumerate(train_loader):
        output = model(b_x)
        loss = loss_func(output, b_y)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        if step % 1000 == 0:
            average_loss = average_loss * 0.95 + loss.item() * 0.05
            print('Epoch:', epoch, '- step:', step, '- loss:', np.round(loss.item(),5), 
                '- average loss:', np.round(average_loss, 5), '- correct:', correct_ratio, '%')
        
    if epoch % 5 == 0:
        correct = 0
        incorrect = 0

        for data, target in test_loader:
            predicted_answer = np.argmax(model.forward(data).detach().numpy())
            right_answer = target[0]
            if int(right_answer) == int(predicted_answer):
                correct+=1
            else:
                incorrect+=1
        print('Test Correct: {}/{}'.format(correct, correct+incorrect))
        correct_ratio = np.round(100 * (correct / (correct+incorrect)), 1)



# Save model function
def saveModel(model):
      
  # 1. Create models directory 
  MODEL_PATH = Path("/Users/muqi/Desktop/Python/PyTorch/Trained Models")
  MODEL_PATH.mkdir(parents=True, exist_ok=True)

  # 2. Create model save path 
  MODEL_NAME = "04_pytorch_face_expression_recognition_model_v3.pth"
  MODEL_SAVE_PATH = MODEL_PATH / MODEL_NAME

  # 3. Save the model state dict 
  print(f"Saving model to: {MODEL_SAVE_PATH}")
  torch.save(obj=model.state_dict(), # only saving the state_dict() only saves the models learned parameters
            f=MODEL_SAVE_PATH) 
  
saveModel(model=model)



"""

COMMENTS ON MODELS


* v1, v2, v3 all used Adam optimiser

v1 (original image):            around 18%      
v2 (cropped image):             around 7%       (probably because of the normalasing, since we didn't rescale but everything was still /96)    --accidentally deleted lol--
v3 (cropped and scaled image):  around 18-23%      (but it does look like it is learning, from epoch 0-30 % went from 5% to 18%, 
                                                                                          then cyclic upwards around 19% and downwards around 16%
                                                                                          with a peak on epoch 80-90 and at the end reaching values around +20%
                                                                                        * it can reach to a peak of 35% with 500 epochs, reaching 30% in epoch 200)
v4 (v3 with SDG optimiser):     

v3:
- Test 1: epochs: 100 | batch size: 16                  --> 18-23%      (from epoch 0-30 % went from 5% to 18%,
                                                                        then cyclic upwards around 19% and downwards around 16%
                                                                        with a peak on epoch 80-90 and at the end reaching values around +20%)

- Test 2: epochs: 500 | batch size: 16                  --> 33-39%      (it surpases 30% in epoch 200,
                                                                        reaching to a peak of 39% around epoch 430)

- Test 3: epochs: 300 | batch size: 32                  --> 30%         (reaching 30% after 250 epochs, with just one 36% peak)
- Test 4: epochs: 500 | batch size: 16 | LR: 0.00001    --> 20%         (not saved)

v4: v3 with SDG optimiser (0.7 momentum)
- Test 1: epochs: 500 | batch size: 16              --> 2.1%        (stucked from the beginning until epoch 50, bugged?? not saved)

"""
