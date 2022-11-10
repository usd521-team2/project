# 
# Group-2 Final Project
#
#

import tensorflow as tf
import mediapipe as mp
import pandas as pd
import seaborn as sns
import numpy as np
import os
import sys
import cv2
import logging
from keras.applications.mobilenet_v3 import preprocess_input
from keras.applications.mobilenet_v3 import decode_predictions
from keras.applications.mobilenet_v3 import MobileNetV3Large
from keras.preprocessing import image
from keras.models import Model
from keras.optimizers import Adam
from keras.layers import Dense, Dropout, Flatten
from tensorflow.keras.preprocessing.image import ImageDataGenerator
from sklearn.model_selection import train_test_split


def capture_gesture():
  """ Capture the ASL hand gesture

  Returns:
      _type_: Cropped Hand Gesture image
  """
  # Setup media pipe capturing gesture    
  mp_drawing = mp.solutions.drawing_utils
  mp_drawing_styles = mp.solutions.drawing_styles
  mp_hands = mp.solutions.hands

  logging.info('Setting up Camera')
  width=1280
  height=720
  cap=cv2.VideoCapture(0,cv2.CAP_DSHOW)
  cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
  cap.set(cv2.CAP_PROP_FRAME_HEIGHT,height)
  cap.set(cv2.CAP_PROP_FPS, 30)
  logging.info('Opening mediapipe')
  with mp_hands.Hands(
      model_complexity=0,
      min_detection_confidence=0.5,
      min_tracking_confidence=0.5) as hands:
    while cap.isOpened():
      success, image = cap.read()
      if not success:
        print("Ignoring empty camera frame.")
        # If loading a video, use 'break' instead of 'continue'.
        continue

      # To improve performance, optionally mark the image as not writeable to
      # pass by reference.
      image.flags.writeable = False
      image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
      h, w, c = image.shape
      results = hands.process(image)

      # Draw the hand annotations on the image.
      image.flags.writeable = True
      image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
      print(results.multi_hand_world_landmarks)
      if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:
          # Get bounding rectangle    
          x_max = 0
          y_max = 0
          x_min = w
          y_min = h
          for lm in hand_landmarks.landmark:
            x, y = int(lm.x * w), int(lm.y * h)
            if x > x_max:
              x_max = x + 25
            if x < x_min:
              x_min = x - 25 
            if y > y_max:
              y_max = y + 25
            if y < y_min:
              y_min = y - 25 
          cv2.rectangle(image, (x_min, y_min), (x_max, y_max), (0, 255, 0), 2)
          hand_crop = image[y_min:y_max, x_min:x_max]
          hand_crop = cv2.flip(hand_crop,1)
          cv2.imwrite('./hand_gesture.png', hand_crop)
          mp_drawing.draw_landmarks(
              image,
              hand_landmarks,
              mp_hands.HAND_CONNECTIONS,
              mp_drawing_styles.get_default_hand_landmarks_style(),
              mp_drawing_styles.get_default_hand_connections_style())
      # Flip the image horizontally for a selfie-view display.
      cv2.imshow('MediaPipe Hands', cv2.flip(image, 1))
      key = cv2.waitKey(5)
      # ESC or 'q'
      if key == 27 or key == 113:
        cv2.destroyAllWindows()
        break
  cap.release()

  return hand_crop

def data_processing(path, img_width, img_height):
  """ Process Data for training and data visualization
  """      
  train_folder = path
  y_col = 'label'
  x_col = 'path'
  all_data = []
  asl_classes = []
  for folder in os.listdir(train_folder):
    asl_classes.append(folder)    
    label_folder = os.path.join(train_folder, folder)
    onlyfiles = [{'label':folder,'path':os.path.join(label_folder, f)} for f in os.listdir(label_folder) if os.path.isfile(os.path.join(label_folder, f))]
    all_data += onlyfiles
  data_df = pd.DataFrame(all_data)

  x_train,x_holdout = train_test_split(data_df, test_size= 0.10, random_state=42,stratify=data_df[['label']])
  x_train,x_test = train_test_split(x_train, test_size= 0.20, random_state=42,stratify=x_train[['label']])

  train_datagen = ImageDataGenerator(
    rescale = 1/255.0,
    preprocessing_function = tf.keras.applications.mobilenet_v2.preprocess_input
  )

  train_generator = train_datagen.flow_from_dataframe(
    dataframe=x_train,x_col=x_col, y_col=y_col,
    target_size=(img_width, img_height),class_mode='categorical', batch_size=batch_size,
    shuffle=False
  )

  validation_datagen = ImageDataGenerator(rescale = 1/255.0)
  validation_generator = validation_datagen.flow_from_dataframe(
    dataframe=x_test, x_col=x_col, y_col=y_col,
    target_size=(img_width, img_height), class_mode='categorical', batch_size=batch_size,
    shuffle=False
  )

  return (train_generator, validation_generator, asl_classes)

def preprocess_image(hand_crop, image_shape):
  """Preprocess Image
  Args:
      hand_crop (image): 
  """
  hand_crop = cv2.resize(hand_crop,(image_shape[0],image_shape[1]))
  cv2.imwrite('./hand_gesture_cropped.png', hand_crop)
  data = np.empty((1,image_shape[0],image_shape[1],image_shape[2]))
  data[0] = hand_crop
  data = preprocess_input(data)
  return data

def create_model_mobileNetv3(input_shape, n_classes, optimizer='rmsprop', fine_tune=0):
    """
    Compiles a model integrated with VGG16 pretrained layers
    
    input_shape: tuple - the shape of input images (width, height, channels)
    n_classes: int - number of classes for the output layer
    optimizer: string - instantiated optimizer to use for training. Defaults to 'RMSProp'
    fine_tune: int - The number of pre-trained layers to unfreeze.
                If set to 0, all pretrained layers will freeze during training
    """
    
    # Pretrained convolutional layers are loaded using the Imagenet weights.
    # Include_top is set to False, in order to exclude the model's fully-connected layers.
    conv_base = MobileNetV3Large(include_top=False,
                     weights='imagenet', 
                     input_shape=input_shape,
                     pooling='avg')
    
    # Defines how many layers to freeze during training.
    # Layers in the convolutional base are switched from trainable to non-trainable
    # depending on the size of the fine-tuning parameter.
    if fine_tune > 0:
        for layer in conv_base.layers[:-fine_tune]:
            layer.trainable = False
    else:
        for layer in conv_base.layers:
            layer.trainable = False

    # Create a new 'top' of the model (i.e. fully-connected layers).
    # This is 'bootstrapping' a new top_model onto the pretrained layers.
    top_model = conv_base.output
    top_model = Flatten(name="flatten")(top_model)
    top_model = Dense(4096, activation='relu')(top_model)
    top_model = Dense(1072, activation='relu')(top_model)
    top_model = Dropout(0.2)(top_model)
    output_layer = Dense(n_classes, activation='softmax')(top_model)
    
    # Group the convolutional base and new fully-connected layers into a Model object.
    model = Model(inputs=conv_base.input, outputs=output_layer)

    # Compiles the model for training.
    model.compile(optimizer=optimizer, 
                  loss='categorical_crossentropy',
                  metrics=['accuracy'])
    
    return model

def train_model(train_dg, val_dg, image_shape, n_classes, batch_size, epochs):
  optim_1 = Adam(learning_rate=0.001)
  model = create_model_mobileNetv3(image_shape, n_classes, optimizer=optim_1)
  history = model.fit(train_dg,
                    batch_size=batch_size,
                    epochs=epochs,
                    verbose=1,
                    validation_data=val_dg)

  return model

def predict_model(model, data, asl_classes):
  # ASL Data Prediction
  predictions = model.predict(data)
  print('Shape: {}'.format(predictions.shape))
  output_neuron = np.argmax(predictions[0])
  print('Most active neuron: {} ({:.2f}%)'.format(
      output_neuron,
      100 * predictions[0][output_neuron]
  ))
  logging.info('Predicted class:' +   str(asl_classes[output_neuron]))


# Globals 
batch_size = 128
epochs = 20
image_shape = (32, 32, 3)
n_classes = 36

# Setup Logging
# Configure the logging system
logging.basicConfig(filename ='group2-final.log',
                    level = logging.INFO)
logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))
# Data processing
logging.info('Data Processing')
(train_dg, val_dg, asl_classes) = data_processing('../../asl_dataset',image_shape[0], image_shape[1])

# Model Training
logging.info('Model Training')
model = train_model(train_dg, val_dg, image_shape, n_classes, batch_size, epochs)
model.summary()  # Uncoomment this to print a long summary!

# ASL Gesture Capture
do_more = ''
while do_more != 'q':
  logging.info('Hand Gesture Capture')
  hand_crop = capture_gesture()
  data = preprocess_image(hand_crop, image_shape)

  # ASL Model Predcition
  logging.info('Gesture Prediction')
  predict_model(model, data, asl_classes)
  do_mode = input('Read another gesture(q to quit)')