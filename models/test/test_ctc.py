#! /usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
import sys
import time
import tensorflow as tf
# from tensorflow.python import debug as tf_debug

sys.path.append(os.path.abspath('../../'))
from models.ctc.vanilla_ctc import CTC
from models.test.util import measure_time
from models.test.data import generate_data, idx2alpha
from utils.io.labels.phone import Idx2phone
from utils.io.labels.sparsetensor import sparsetensor2list
from utils.parameter import count_total_parameters
from utils.training.learning_rate_controller import Controller


class TestCTC(tf.test.TestCase):

    def test_ctc(self):
        print("CTC Working check.")

        ##############################
        # VGG-CTC
        ##############################
        # self.check_training(encoder_type='vgg_wang', label_type='phone',
        #                     lstm_impl=None)
        # self.check_training(encoder_type='vgg_wang', label_type='character',
        #                     lstm_impl=None)

        ##############################
        # CNN-CTC
        ##############################
        # self.check_training(encoder_type='cnn_zhang', label_type='phone',
        #                     lstm_impl=None)
        # self.check_training(encoder_type='cnn_zhang', label_type='character',
        #                     lstm_impl=None)

        ##############################
        # BLSTM-CTC
        ##############################
        # self.check_training(encoder_type='blstm', label_type='phone',
        #                     lstm_impl='BasicLSTMCell')
        self.check_training(encoder_type='blstm', label_type='phone',
                            lstm_impl='LSTMCell')
        # self.check_training(encoder_type='blstm', label_type='phone',
        #                     lstm_impl='LSTMBlockCell')
        # self.check_training(encoder_type='blstm', label_type='character',
        #                     save_params=True)

        # self.check_training(encoder_type='blstm', label_type='phone',
        #                     lstm_impl='CudnnLSTM')
        # self.check_training(encoder_type='blstm', label_type='phone',
        #                     lstm_impl='LSTMBlockFusedCell')

        ##############################
        # LSTM-CTC
        ##############################
        # self.check_training(encoder_type='lstm', label_type='phone',
        #                     lstm_impl='BasicLSTMCell')
        self.check_training(encoder_type='lstm', label_type='phone',
                            lstm_impl='LSTMCell')
        # self.check_training(encoder_type='lstm', label_type='phone',
        #                     lstm_impl='LSTMBlockCell')
        # self.check_training(encoder_type='lstm', label_type='character')

        # self.check_training(encoder_type='lstm', label_type='phone',
        #                     lstm_impl='CudnnLSTM')
        # self.check_training(encoder_type='lstm', label_type='phone',
        #                     lstm_impl='LSTMBlockFusedCell')

        ##############################
        # VGG-BLSTM-CTC
        ##############################
        self.check_training(encoder_type='vgg_blstm', label_type='phone')
        self.check_training(encoder_type='vgg_blstm', label_type='character')

        ##############################
        # VGG-LSTM-CTC
        ##############################
        self.check_training(encoder_type='vgg_lstm', label_type='phone')
        self.check_training(encoder_type='vgg_lstm', label_type='character')

        ##############################
        # BGRU-CTC
        ##############################
        self.check_training(encoder_type='bgru', label_type='phone')
        self.check_training(encoder_type='bgru', label_type='character')

        ##############################
        # GRU-CTC
        ##############################
        self.check_training(encoder_type='gru', label_type='phone')
        self.check_training(encoder_type='gru', label_type='character')

    @measure_time
    def check_training(self, encoder_type, label_type,
                       lstm_impl='LSTMBlockCell', save_params=False):

        print('==================================================')
        print('  encoder_type: %s' % encoder_type)
        print('  label_type: %s' % label_type)
        print('  lstm_impl: %s' % lstm_impl)
        print('==================================================')

        tf.reset_default_graph()
        with tf.Graph().as_default():
            # Load batch data
            batch_size = 1
            splice = 11 if encoder_type in ['vgg_blstm', 'vgg_lstm', 'vgg_wang',
                                            'resnet_wang', 'cnn_zhang'] else 1
            inputs, labels_true_st, inputs_seq_len = generate_data(
                label_type=label_type,
                model='ctc',
                batch_size=batch_size,
                splice=splice)
            # NOTE: input_size must be even number when using CudnnLSTM

            # Define model graph
            num_classes = 26 if label_type == 'character' else 61
            model = CTC(encoder_type=encoder_type,
                        input_size=inputs[0].shape[-1] // splice,
                        splice=splice,
                        num_units=256,
                        num_layers=2,
                        num_classes=num_classes,
                        lstm_impl=lstm_impl,
                        parameter_init=0.1,
                        clip_grad=5.0,
                        clip_activation=50,
                        num_proj=256,
                        # bottleneck_dim=50,
                        bottleneck_dim=None,
                        weight_decay=1e-8)

            # Define placeholders
            model.create_placeholders()
            learning_rate_pl = tf.placeholder(tf.float32, name='learning_rate')

            # Add to the graph each operation
            loss_op, logits = model.compute_loss(
                model.inputs_pl_list[0],
                model.labels_pl_list[0],
                model.inputs_seq_len_pl_list[0],
                model.keep_prob_input_pl_list[0],
                model.keep_prob_hidden_pl_list[0],
                model.keep_prob_output_pl_list[0])
            train_op = model.train(loss_op,
                                   optimizer='adam',
                                   learning_rate=learning_rate_pl)
            # NOTE: Adam does not run on CudnnLSTM
            decode_op = model.decoder(logits,
                                      model.inputs_seq_len_pl_list[0],
                                      beam_width=20)
            ler_op = model.compute_ler(decode_op, model.labels_pl_list[0])

            # Define learning rate controller
            learning_rate = 1e-3
            lr_controller = Controller(learning_rate_init=learning_rate,
                                       decay_start_epoch=10,
                                       decay_rate=0.98,
                                       decay_patient_epoch=5,
                                       lower_better=True)

            if save_params:
                # Create a saver for writing training checkpoints
                saver = tf.train.Saver(max_to_keep=None)

            # Add the variable initializer operation
            init_op = tf.global_variables_initializer()

            # Count total parameters
            if lstm_impl != 'CudnnLSTM':
                parameters_dict, total_parameters = count_total_parameters(
                    tf.trainable_variables())
                for parameter_name in sorted(parameters_dict.keys()):
                    print("%s %d" %
                          (parameter_name, parameters_dict[parameter_name]))
                print("Total %d variables, %s M parameters" %
                      (len(parameters_dict.keys()),
                       "{:,}".format(total_parameters / 1000000)))

            # Make feed dict
            feed_dict = {
                model.inputs_pl_list[0]: inputs,
                model.labels_pl_list[0]: labels_true_st,
                model.inputs_seq_len_pl_list[0]: inputs_seq_len,
                model.keep_prob_input_pl_list[0]: 1.0,
                model.keep_prob_hidden_pl_list[0]: 1.0,
                model.keep_prob_output_pl_list[0]: 1.0,
                learning_rate_pl: learning_rate
            }

            idx2phone = Idx2phone(map_file_path='./phone61_ctc.txt')

            with tf.Session() as sess:
                # Initialize parameters
                sess.run(init_op)

                # Wrapper for tfdbg
                # sess = tf_debug.LocalCLIDebugWrapperSession(sess)

                # Train model
                max_steps = 1000
                start_time_global = time.time()
                start_time_step = time.time()
                ler_train_pre = 1
                not_improved_count = 0
                for step in range(max_steps):

                    # Compute loss
                    _, loss_train = sess.run(
                        [train_op, loss_op], feed_dict=feed_dict)

                    # Gradient check
                    # grads = sess.run(model.clipped_grads,
                    #                  feed_dict=feed_dict)
                    # for grad in grads:
                    #     print(np.max(grad))

                    if (step + 1) % 10 == 0:
                        # Change to evaluation mode
                        feed_dict[model.keep_prob_input_pl_list[0]] = 1.0
                        feed_dict[model.keep_prob_hidden_pl_list[0]] = 1.0
                        feed_dict[model.keep_prob_output_pl_list[0]] = 1.0

                        # Compute accuracy
                        ler_train = sess.run(ler_op, feed_dict=feed_dict)

                        duration_step = time.time() - start_time_step
                        print('Step %d: loss = %.3f / ler = %.3f (%.3f sec) / lr = %.5f' %
                              (step + 1, loss_train, ler_train, duration_step, learning_rate))
                        start_time_step = time.time()

                        # Decode
                        labels_pred_st = sess.run(
                            decode_op, feed_dict=feed_dict)
                        labels_true = sparsetensor2list(
                            labels_true_st, batch_size=batch_size)

                        # Visualize
                        try:
                            labels_pred = sparsetensor2list(
                                labels_pred_st, batch_size=batch_size)
                            if label_type == 'character':
                                print('Ref: %s' % idx2alpha(labels_true[0]))
                                print('Hyp: %s' % idx2alpha(labels_pred[0]))
                            else:
                                print('Ref: %s' % idx2phone(labels_true[0]))
                                print('Hyp: %s' % idx2phone(labels_pred[0]))

                        except IndexError:
                            if label_type == 'character':
                                print('Ref: %s' % idx2alpha(labels_true[0]))
                                print('Hyp: %s' % '')
                            else:
                                print('Ref: %s' % idx2phone(labels_true[0]))
                                print('Hyp: %s' % '')
                            # NOTE: This is for no prediction

                        if ler_train >= ler_train_pre:
                            not_improved_count += 1
                        else:
                            not_improved_count = 0
                        if ler_train < 0.05:
                            print('Modle is Converged.')
                            if save_params:
                                # Save model (check point)
                                checkpoint_file = './model.ckpt'
                                save_path = saver.save(
                                    sess, checkpoint_file, global_step=1)
                                print("Model saved in file: %s" % save_path)
                            break
                        ler_train_pre = ler_train

                        # Update learning rate
                        learning_rate = lr_controller.decay_lr(
                            learning_rate=learning_rate,
                            epoch=step,
                            value=ler_train)
                        feed_dict[learning_rate_pl] = learning_rate

                duration_global = time.time() - start_time_global
                print('Total time: %.3f sec' % (duration_global))


if __name__ == "__main__":
    tf.test.main()
