import copy
import os
import time
import pandas as pd
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset, BatchSampler, RandomSampler
import pandas as pd
import altair as alt
import copy
import streamlit as st
from datetime import datetime
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
import streamlit as st
import altair as alt
import matplotlib
import matplotlib.pyplot as plt
matplotlib.use('module://drawilleplot')

class ai:

    # settings / object properties
    features = ['feature1', 'feature2', 'feature3']             # replace these at run time with the feature list from the data object!
    target = "target_feature1"                                  # this is what we are predicting, also supplied via the data object
    training_split = 0.05                                       # controls the amount of data to use for train/test
    model = None                                                # placeholder for the model once it has been initialized
    model_top = None                                            # placeholder for the top scoring model
    model_top_loss = 100                                        # placeholding for the current top model's test loss
    model_filename_root = "../models/"                    # default model filename
    model_filename = None                                       # placeholder for model filename
    model_size = 100                                            # number of parameters for the hidden network layer
    training_epochs = 15                                      # default number of epochs to train the network for
    training_batch_size = 200000                                # number of records we *think* we can fit into the GPU...
    training_workers = 16                                       # number of dataloader workers to use for loading training data into the GPU
    testing_workers = 4                                         # numer of dataloader workers to use for loading test data into the GPU
    weight_decay = 0.001                                        # optimizer weight decay        
    dropout = 0.15                                              # % of neurons to apply dropout to                                        
    target_loss = 100                                           # keep training until either the epoch limit is hit or test loss is lower than this number
    training_learning_rate = 0.035                              # default network learning rate
    test_interval = 5                                         # model testing interval during training
    pdiffGoal = 0.15
    x_train = None
    y_train = None
    x_test = None
    y_test = None                        

    def __init__(self) -> None:
        
        # setup GPU
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        if(self.device == "cuda"):
            torch.cuda.init()
            print("Using ", self.device)

    def get_model_list(self, path, extension='pt'): # def get_model_list(self, path, extension='pkl'):
        # returns a list of models in the specified path
        matching_files = []
        if not extension.startswith('.'):
            extension = '.' + extension
        
        for root, dirs, files in os.walk(path):
            for file in files:
                if file.endswith(extension):
                    matching_files.append(os.path.join(root, file))
        
        return matching_files
    
    def set_max_batch_size(self, x_train, y_train):
        print("Determining optimal batch size...")
        model = self.model.to(self.device)
        batch_size = self.training_batch_size
        max_memory_used = 0
        acceptable_memory = torch.cuda.get_device_properties(self.device).total_memory * 0.8

        while True:
            try:
                # Create DataLoader with the current batch size for each iteration
                train_loader = DataLoader(TensorDataset(x_train, y_train), batch_size=batch_size, shuffle=True)
                
                print("Testing batch size:", batch_size)

                for x_batch, y_batch in train_loader:
                    x_batch, y_batch = x_batch.to(self.device), y_batch.to(self.device)
                    with torch.no_grad():
                        output = model(x_batch)
                    break # stop after one pass

                memory_used = torch.cuda.memory_allocated(self.device)
                if memory_used < acceptable_memory and memory_used > max_memory_used:
                    max_memory_used = memory_used
                    batch_size *= 2  # Increase batch size
                else:
                    break  # If memory exceeds acceptable limit or no more improvement, stop increasing
            except RuntimeError as e:
                if 'out of memory' in str(e):
                    print("CUDA out of memory with batch size:", batch_size)
                    batch_size //= 2  # Halve the batch size if out of memory
                    if batch_size < 1:
                        break
                else:
                    raise e

        model = None
        torch.cuda.empty_cache()  # Clear memory cache
        self.training_batch_size = batch_size

    def format_training_data(self, dataframe):
        # formats features for input into the model
        # NOTE: this is not where the primary data features are created, that is performed within the data module itself.
        X = dataframe[self.features]
        y = dataframe[self.target]

        # data sanity checks
        if X.isnull().values.any():
            print("WARNING: Null values detected in training data!")
        
        if np.isinf(X).values.any():
            print("WARNING: Infinate values detected!")

        if X.duplicated().any():
            print(f'Duplicates: {len(X[X.duplicated()])}')
            print("WARNING: Duplicate rows detected!")

        # Split the data into training and testing sets
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=self.training_split, random_state=42,)

        # Output some basic debug info
        print("Training set size is", len(X_train),"records.")
        print("Test set size is", len(y_test),"records.")

        # Standardize the features
        scaler = StandardScaler()
        X_train = scaler.fit_transform(X_train)
        X_test = scaler.transform(X_test)

        # Convert the data to PyTorch tensors
        X_train_tensor = torch.tensor(X_train.astype(np.float32))
        y_train_tensor = torch.tensor(y_train.values.astype(np.float32)).view(-1, 1)
        X_test_tensor = torch.tensor(X_test.astype(np.float32))
        y_test_tensor = torch.tensor(y_test.values.astype(np.float32)).view(-1, 1)

        # save these tensors to model object
        self.x_train = X_train_tensor
        self.y_train = y_train_tensor
        self.x_test = X_test_tensor
        self.y_test = y_test_tensor

        return X_train_tensor, y_train_tensor, X_test_tensor, y_test_tensor
    
    def model_init(self, x_dim):
        # Initialize the neural network
        input_size = x_dim.shape[1]
        self.model = LinearNN(input_size, self.model_size, self.dropout)
        self.model.to(self.device)
        return 
    
    def model_load(self, x_dim, filename=model_filename):
        # loads the model using specified filename
        self.model_init(x_dim)
        print("Loading model:", self.model_filename)
        if self.model.load_model_for_inference(self.model_filename):
            self.model.to(self.device)
            return True
        else:
            return False
    
    def model_save(self, model):
        # triggers the model save process
        # makes models folder if it does not exist
        if not os.path.exists(self.model_filename_root):
            os.makedirs(self.model_filename_root)
        model.save((self.model_filename_root + 'model_'))
        self.model_filename = self.model_filename_root + ".pkl"

    def calculate_accuracy(self, predicted, known):
        # move data back to main memory for CPU processing
        predicted_cpu = predicted.cpu()
        known_cpu = known.cpu()

        if predicted_cpu.shape != known_cpu.shape:
            raise ValueError("The two tensors must be of the same shape!")

        print(known_cpu.shape[0])

        SST = torch.sum(torch.pow(known_cpu - torch.mean(known_cpu), 2))
        SSR = torch.sum(torch.pow((known_cpu - predicted_cpu), 2))

        percDiff = torch.divide(torch.abs(torch.sub(known_cpu, predicted_cpu)), known_cpu)

        plt.figure()
        plt.hist(100*percDiff[percDiff.isfinite()], bins=[i for i in range(0, 155, 5)])
        plt.title('Distribution of Percent Difference between Expected and Predicted')
        plt.show()
        plt.close()

        numBelow10 = percDiff[percDiff < self.pdiffGoal]
        percBelow = 100 * numBelow10.shape[0] / known.shape[0]

        return 1 - SSR / SST, percBelow
    
    def plot_convergence(self, predicted, known):
        # Ensure tensors are moved to CPU before plotting
        predicted_cpu = predicted.cpu()
        known_cpu = known.cpu()

        plt.figure()
        plt.plot(known_cpu, predicted_cpu, 'k.')
        plt.ylim(top=int(torch.max(known_cpu) + (0.10 * torch.max(known_cpu))))
        plt.show()
        plt.close()

    def train(self, model, x_train, y_train, x_test, y_test, epochs=training_epochs, learning_rate=training_learning_rate):
        # Check if multiple GPUs are available and wrap the model using DataParallel
        if torch.cuda.device_count() > 1:
            print(f"Let's use {torch.cuda.device_count()} GPUs!")
            torch.cuda.synchronize()
            model = nn.DataParallel(model)

        # Send model to device (will be GPU if CUDA is available)
        model.to(self.device)

        # Convert training and testing data into PyTorch datasets and dataloaders
        train_dataset = TensorDataset(x_train, y_train)
        train_loader = DataLoader(dataset=train_dataset, batch_size=self.training_batch_size, shuffle=True, num_workers=self.training_workers, pin_memory=True)
        test_dataset = TensorDataset(x_test, y_test)
        test_loader = DataLoader(dataset=test_dataset, batch_size=self.training_batch_size, shuffle=False, num_workers=self.testing_workers, pin_memory=True)

        # Define the loss function and optimizer
        criterion = nn.HuberLoss(delta=500)
        optimizer = optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=self.weight_decay)

        # Place chart plotting epochs in a streamlit window
        col3, col4 = st.columns([1,1])
        with col4:
            pass
        with col3:
            # Initialize Plotting of Epoch and Loss
            data = pd.DataFrame({'Epoch': [], 'Loss':[]})
            chart = alt.Chart(data).mark_line(color='red').encode(
                x=alt.X('Epoch', scale=alt.Scale(domain=(0, epochs)), axis=alt.Axis(title='Epochs')),
                y=alt.Y('Loss', scale=alt.Scale(type='log'), axis=alt.Axis(title='Logarithmic Loss'))
            ).properties(title='Logarithmic Loss vs Epochs')
            alt_chart = st.altair_chart(chart, use_container_width=False)
            
            # Training loop
            for epoch in range(epochs):
                epoch_start = time.time()  # Start time of the epoch
                model.train()
                total_loss = 0
                for x_batch, y_batch in train_loader:
                    x_batch, y_batch = x_batch.to(self.device, non_blocking=True), y_batch.to(self.device, non_blocking=True)
                    # Forward pass
                    outputs = model(x_batch)
                    loss = criterion(outputs, y_batch)
                    # Backward pass and optimization
                    optimizer.zero_grad()
                    loss.backward()
                    optimizer.step()
                    total_loss += loss.item()

                average_loss = total_loss / len(train_loader)
                epoch_duration = time.time() - epoch_start  # Calculate duration of the epoch

                # Update and display the chart
                new_data = pd.DataFrame({'Epoch': [epoch], 'Loss': [average_loss]})
                data = pd.concat([data, new_data], ignore_index=True) 
                chart = alt.Chart(data).mark_line(color='red').encode(
                    x=alt.X('Epoch', scale=alt.Scale(domain=(0, epochs)), axis=alt.Axis(title='Epochs')), 
                    y=alt.Y('Loss', scale=alt.Scale(type='log'), axis=alt.Axis(title='Logarithmic Loss'))
                )
                alt_chart.altair_chart(chart)

                print(f'Epoch [{epoch+1}/{epochs}], Loss: {average_loss:.4f}, Time: {epoch_duration:.2f} sec')

                if (epoch+1) % self.test_interval == 0:
                    predictions, y_test, test_loss, test_accuracy  = self.test(model, test_loader)
                    self.plot_convergence(predictions, y_test)
                
                    print(f'  Test Loss: {test_loss}; Test Accuracy: {test_accuracy}')

                    # if the loss is less, copy the weights, if we have hit the target loss, save the model and end training
                    if epoch+1 == self.test_interval:
                        self.model_top_loss = test_loss
                        self.model_top = copy.deepcopy(model.module if isinstance(model, nn.DataParallel) else model)
                    if test_loss < self.model_top_loss:
                        self.model_top = copy.deepcopy(model.module if isinstance(model, nn.DataParallel) else model)
                        self.model_top_loss = test_loss
                        if test_loss <= self.target_loss:
                            print("Early stopping!")
                            self.model_save(self.model_top)
                            return

            # Final model saving after training
            self.model_save(self.model_top)
            self.model = self.model_top


    def test(self, model, test_loader):
        criterion = nn.MSELoss()
        model.eval()

        total_loss = 0
        all_predictions = []
        all_y_test = []

        with torch.no_grad():
            for x_batch, y_batch in test_loader:
                x_batch, y_batch = x_batch.to(self.device, non_blocking=True), y_batch.to(self.device, non_blocking=True)
                predictions = model(x_batch)
                test_loss = criterion(predictions, y_batch)
                total_loss += test_loss.item()

                all_predictions.append(predictions)
                all_y_test.append(y_batch)

        # Concatenate all batches for calculating accuracy and other metrics
        all_predictions = torch.cat(all_predictions, dim=0)
        all_y_test = torch.cat(all_y_test, dim=0)

        R2, Within10 = self.calculate_accuracy(all_predictions, all_y_test)
        average_test_loss = total_loss / len(test_loader)

        # print(all_predictions)
        # print(all_y_test)
        print(f'Test Loss: {average_test_loss}, R2: {R2}, {Within10}% are within {100*self.pdiffGoal} Percent of Expected')
        
        return all_predictions, all_y_test, average_test_loss, (R2, Within10)

    def predict(self, model, data):
        scaler = StandardScaler()
        data = scaler.transform(data[self.features])
        segments_without_counts_tensor = torch.tensor(data.astype(np.float32))
        with torch.no_grad():
            predicted_counts = model(segments_without_counts_tensor)
            return predicted_counts

# *Somewhat* simple neural network!
class LinearNN(nn.Module):
    def __init__(self, input_size, layer_size, dropout):
        super(LinearNN, self).__init__()
        self.fc1 = nn.Linear(input_size, int(layer_size*2))
        self.bn1 = nn.BatchNorm1d(int(layer_size*2))
        self.fc2 = nn.Linear(int(layer_size*2), layer_size)
        self.bn2 = nn.BatchNorm1d(layer_size)
        self.fc3 = nn.Linear(int(layer_size), layer_size)
        self.bn3 = nn.BatchNorm1d(layer_size)
        self.fc4 = nn.Linear(layer_size, layer_size // 2)  # Reduce layer size
        self.bn4 = nn.BatchNorm1d(layer_size // 2)
        self.fc5 = nn.Linear(layer_size // 2, 1)  # Output layer for regression

        # Optional: add dropout for regularization
        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        x = F.relu(self.bn1(self.fc1(x)))
        # x = self.dropout(x)
        x = F.relu(self.bn2(self.fc2(x)))
        x = self.dropout(x)
        x = F.relu(self.bn3(self.fc3(x)))
        x = self.dropout(x)
        x = F.relu(self.bn4(self.fc4(x)))
        # x = self.dropout(x)
        x = self.fc5(x)  # No activation function here as it's a regression task

        return x
    
    # Function to save the model
    def save(self, filename):
        filename = self.create_filename(filename)

        # save the entire model for stand-alone inference later
        model_jit = torch.jit.script(self)
        model_jit.save(filename + ".pt")
        print(f"Model file saved to {filename}")

        return True
        
    def load_model_for_inference(self, filename):
        try:
            # Load the entire JIT-compiled model
            self.model = torch.jit.load(filename, map_location=torch.device('cpu'))
            # Switch the model to evaluation mode
            self.model.eval()
            print(f"Model loaded from {filename}")
            return True
        except Exception as e:
            # Print the exception and return False if any error occurs
            print(e)
            return False
    
    def create_filename(self, filename):
        current_datetime = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{filename}_{current_datetime}"