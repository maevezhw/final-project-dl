import streamlit as st
from music21 import converter, instrument, note, chord, stream, duration, midi
import IPython
from midi2audio import FluidSynth
from keras.models import load_model
import numpy as np
import pandas as pd
import os
import keras.utils
from fractions import Fraction
import tempfile
import subprocess

def generate_music(input_path, output_name):
  def train_learning():
    notes_path = 'notes_train.txt'
    durations_path = 'durations_train.txt'

    notes_train = []
    durations_train = []
    # Open the file in read mode

    with open(notes_path, 'r') as file:
        # Read the file line by line and save each line in a list
        for line in file:
            # Remove leading and trailing whitespace, including newline characters
            cleaned_line = line.strip()

            # Process the cleaned line if needed
            notes_train.append(cleaned_line)

    with open(durations_path, 'r') as file:
        # Read the file line by line and save each line in a list
        for line in file:
            # Remove leading and trailing whitespace, including newline characters
            cleaned_line = line.strip()

            try:
              cleaned_line = float(cleaned_line)

            except Exception as e:
              cleaned_line = Fraction(cleaned_line)
            # Process the cleaned line if needed

            durations_train.append(float(cleaned_line))

    combined_train = list(zip(notes_train, durations_train))

    # get all unique combined pitch and duration pairs
    unique_pairs_train = sorted(set(item for item in combined_train))

    # create a dictionary to map unique pairs to integers
    pair_to_int = {pair: number for number, pair in enumerate(unique_pairs_train)}

    return combined_train, unique_pairs_train, pair_to_int

  def generate_data(input_path):
    notes_test = []
    durations_test = []

    midi = converter.parse(input_path)
    prev_offset = 0.0

    for element in midi.flat.notes:
      if isinstance(element, note.Note):
        notes_test.append(str(element.pitch))
        duration = element.duration.quarterLength
        durations_test.append(duration)
      elif isinstance(element, chord.Chord):
        notes_test.append(".".join(str(n) for n in element.normalOrder))
        duration = element.duration.quarterLength
        durations_test.append(duration)
        prev_offset = element.offset + element.duration.quarterLength

    return notes_test, durations_test

  def make_input(input_path):
    sequence_length = 25
    notes_test, durations_test = generate_data(input_path)
    combined_train, unique_pairs_train, pair_to_int = train_learning()

    network_input_test = []
    network_output_test = []

    # create input sequences and corresponding outputs
    for i in range(0, len(combined_train) - sequence_length, 1):
        sequence_in = combined_train[i:i + sequence_length]
        sequence_out = combined_train[i + sequence_length]

        # map pitches and durations to their integer representations
        network_input_test.append([pair_to_int[pair] for pair in sequence_in])
        network_output_test.append(pair_to_int[sequence_out])

    n_patterns = len(network_input_test)

    # reshape the input into a format compatible with LSTM layers
    network_input_test = np.reshape(network_input_test, (n_patterns, sequence_length, 1))

    # normalize input
    network_input_test = network_input_test / float(len(unique_pairs_train))

    # one-hot encode the output (since it represents both pitch and duration)
    network_output_test = keras.utils.to_categorical(network_output_test, num_classes=len(unique_pairs_train))
    return network_input_test, network_output_test

  def predict(input_path):
    network_input_test, network_output_test = make_input(input_path)
    model_path = 'lastmodel-seq25-val-94-1.2518-bigger.h5'
    model = load_model(model_path)

    combined_notes_durations, unique_pairs_train, pair_to_int = train_learning()
    int_to_pair = {number: pair for pair, number in pair_to_int.items()}
    start = np.random.randint(0, len(network_input_test)-1)
    pattern = network_input_test[start]

    prediction_output = []

    # generate notes
    for note_index in range(100):
        prediction_input = np.reshape(pattern, (1, len(pattern), 1))
        prediction = model.predict(prediction_input, verbose=0)
        index = np.argmax(prediction)

        result = int_to_pair[index]  # Retrieve the note-duration pair from the integer index
        prediction_output.append(result)

        # Update pattern for the next iteration
        to_append = index / float(len(unique_pairs_train))
        pattern = np.append(pattern, [[to_append]], axis=0)
        pattern = pattern[1:len(pattern)]

    return prediction_output


  def generate_midi(input_path):
    prediction_output = predict(input_path)

    offset = 0
    output_notes = []
    output_stream = stream.Stream()
    # create note and chord objects based on the values generated by the model
    for pattern in prediction_output:
      note_pitch, note_duration = pattern

      # Check if the note_pitch is a float (representing a note duration) and handle accordingly
      if isinstance(note_pitch, float):
          # Assuming the previous note was a chord, end it and start a new note with a duration
          output_stream[-1].duration.quarterLength = note_pitch
      else:
          if '.' in note_pitch:  # If it's a chord
              notes_in_chord = note_pitch.split('.')
              chord_notes = []
              for current_note in notes_in_chord:
                  new_note = note.Note(int(current_note))
                  new_note.duration.quarterLength = note_duration
                  chord_notes.append(new_note)
              new_chord = chord.Chord(chord_notes)
              output_stream.append(new_chord)
          else:  # If it's a single note
              try:
                  new_note = note.Note(note_pitch)
                  new_note.duration.quarterLength = note_duration
                  output_stream.append(new_note)
              except Exception as e:
                  pass

    # Write the MIDI file
    midi_stream = midi.translate.music21ObjectToMidiFile(output_stream)

    return midi_stream

  midi_stream = generate_midi(input_path)
  midi_stream.open('generated_music1.mid', 'wb')
  midi_stream.write()
  midi_stream.close()

  fs = FluidSynth()
  fs.midi_to_audio('generated_music1.mid', output_name)

st.title("Generate Classical Music Based on MIDI File")

midi_file = st.file_uploader("Upload MIDI File", type=["mid"])

if st.sidebar.button("Generate Audio"):
    if midi_file is not None:
        with tempfile.NamedTemporaryFile(delete=False, suffix = '.mid') as temp_file:
            temp_file.write(midi_file.read())

        # st.success(f"File successfully uploaded and saved at: {temp_file.name}")


        st.sidebar.success("Generating Audio...")
        audio_new = generate_music(temp_file.name, 'output.wav')

        st.header('Generated Audio')
        st.audio('output.wav')
    else:
        st.sidebar.error("Please upload a midi file")