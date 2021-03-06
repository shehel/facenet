# coding=utf-8
"""Face Detection and Recognition"""
# MIT License
#
# Copyright (c) 2017 François Gervais
#
# This is the work of David Sandberg and shanren7 remodelled into a
# high level container. It's an attempt to simplify the use of such
# technology and provide an easy to use facial recognition package.
#
# https://github.com/davidsandberg/facenet
# https://github.com/shanren7/real_time_face_recognition
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
import hnswlib
import pickle
import os

import cv2
import numpy as np
import tensorflow as tf
from scipy import misc
from scipy.spatial import distance

import align.detect_face
import facenet
import pdb

gpu_memory_fraction = 0.3
facenet_model_checkpoint = os.path.dirname(__file__) + "/../model_checkpoints/20170512-110547"
classifier_model = os.path.dirname(__file__) + "/../model_checkpoints/my_classifier_1.pkl"
debug = False


class Face:
    def __init__(self):
        self.name = None
        self.bounding_box = None
        self.image = None
        self.container_image = None
        self.embedding = None


class Recognition:
    def __init__(self):
        self.detect = Detection()
        self.encoder = Encoder()
        self.identifier = Identifier(128, 200)

    def add_identity(self, image, person_name):
        faces = self.detect.find_faces(image)

        if len(faces) == 1:
            face = faces[0]
            face.name = person_name
            face.embedding = self.encoder.generate_embedding(face)
            return faces

    def identify(self, image):
        faces = self.detect.find_faces(image)
        
        for i, face in enumerate(faces):
            if debug:
                cv2.imshow("Face: " + str(i), face.image)
            face.embedding = self.encoder.generate_embedding(face)
            face.name = self.identifier.identify(face)

        return faces


class Identifier:
    def __init__(self, dim, num_elements):
        self.dim = dim
        self.num_elements = num_elements
        self.p = hnswlib.Index(space='l2', dim=self.dim)
        self.p.init_index(max_elements = num_elements, ef_construction = 200, M = 16)
        self.p.set_ef(50)
        self.p.add_items(np.ones(shape=(128)), 0)
        self.current_id = 1
        with open('comb') as f:
            self.names = f.read().splitlines()
        self.faces_in_frame = []
        self.id_in_frame = []
        self.faces_in_frame.append(tuple([0,0,0,0]))
        self.id_in_frame.append(0)
    def identify(self, face):
        if face.embedding is not None:
            labels, distances = self.p.knn_query(face.embedding, k = 1)
            # print (distances[0][0])
            closest_dist = 5
            if self.faces_in_frame:
                euclidean = distance.cdist([tuple(face.bounding_box)], self.faces_in_frame)
                closest_dist = np.min(euclidean)
                closest_match = np.argmin(euclidean)
                print (distances)
            if distances[0][0] < 0.6:
                change_idx = self.id_in_frame.index(labels[0][0])
                self.faces_in_frame[change_idx]=(tuple(face.bounding_box))
                return str(labels[0][0])
            elif closest_dist < 1 and id_in_frame[closest_match] == labels[0][0]:
                change_idx = self.id_in_frame.index(labels[0][0])
                self.faces_in_frame[change_idx]=(tuple(face.bounding_box))
                self.p.add_items(face.embedding, labels[0][0])
                return str(labels[0][0])
            else:
                # if self.current_id>1:
                #     pdb.set_trace()
                if not self.id_in_frame[closest_match] == self.current_id:
                    self.faces_in_frame.append(tuple(face.bounding_box))
                    self.id_in_frame.append(self.current_id)
                else:
                    self.p.add_items(face.embedding, self.current_id)
                    self.faces_in_frame.append(tuple(face.bounding_box))
                    self.id_in_frame.append(self.current_id)
                    self.current_id += 1
            #pdb.set_trace()
                
            #if labels:
            #    print (labels, distances)
            #return self.class_names[best_class_indices[0]]


class Encoder:
    def __init__(self):
        self.sess = tf.Session()
        with self.sess.as_default():
            facenet.load_model(facenet_model_checkpoint)

    def generate_embedding(self, face):
        # Get input and output tensors
        images_placeholder = tf.get_default_graph().get_tensor_by_name("input:0")
        embeddings = tf.get_default_graph().get_tensor_by_name("embeddings:0")
        phase_train_placeholder = tf.get_default_graph().get_tensor_by_name("phase_train:0")

        prewhiten_face = facenet.prewhiten(face.image)

        # Run forward pass to calculate embeddings
        feed_dict = {images_placeholder: [prewhiten_face], phase_train_placeholder: False}
        return self.sess.run(embeddings, feed_dict=feed_dict)[0]


class Detection:
    # face detection parameters
    minsize = 20  # minimum size of face
    threshold = [0.6, 0.7, 0.7]  # three steps's threshold
    factor = 0.709  # scale factor

    def __init__(self, face_crop_size=160, face_crop_margin=32):
        self.pnet, self.rnet, self.onet = self._setup_mtcnn()
        self.face_crop_size = face_crop_size
        self.face_crop_margin = face_crop_margin

    def _setup_mtcnn(self):
        with tf.Graph().as_default():
            gpu_options = tf.GPUOptions(per_process_gpu_memory_fraction=gpu_memory_fraction)
            sess = tf.Session(config=tf.ConfigProto(gpu_options=gpu_options, log_device_placement=False))
            with sess.as_default():
                return align.detect_face.create_mtcnn(sess, None)

    def find_faces(self, image):
        faces = []

        bounding_boxes, _ = align.detect_face.detect_face(image, self.minsize,
                                                          self.pnet, self.rnet, self.onet,
                                                          self.threshold, self.factor)
        for bb in bounding_boxes:
            face = Face()
            face.container_image = image
            face.bounding_box = np.zeros(4, dtype=np.int32)

            img_size = np.asarray(image.shape)[0:2]
            face.bounding_box[0] = np.maximum(bb[0] - self.face_crop_margin / 2, 0)
            face.bounding_box[1] = np.maximum(bb[1] - self.face_crop_margin / 2, 0)
            face.bounding_box[2] = np.minimum(bb[2] + self.face_crop_margin / 2, img_size[1])
            face.bounding_box[3] = np.minimum(bb[3] + self.face_crop_margin / 2, img_size[0])
            cropped = image[face.bounding_box[1]:face.bounding_box[3], face.bounding_box[0]:face.bounding_box[2], :]
            face.image = misc.imresize(cropped, (self.face_crop_size, self.face_crop_size), interp='bilinear')

            faces.append(face)

        return faces
