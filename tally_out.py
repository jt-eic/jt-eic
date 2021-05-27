#!/usr/bin/env python3
""" The name 'tally out' refers to the function of reading in a tone signal
and triggering a contact closure for the purpose of camera tally signals.

This version is built to receive a mono audio signal input, setup on a Raspberry Pi
with a USB audio microphone adapter or similar. Raspberry Pi's do not have any audio
input hardware by default, so you need to provide one.

Additionally, the pins on the Pi are not suitable to directly trigger the closure circuit.
This requires at least ONE, or up to TWO relays (single pole, single throw, Normal Open) or
a MOSFET wired up as a solid state relay will also work.

For 2 tally operation, make sure that the tone signals passed in are both on the same channel
as mono, and lower the gain of the 2nd channel to aprox. -20 db.  This will be enough separation
between them so it will detect the difference. If they are all over the place (usually just both
firing the same tally no matter how low the gain is) then adjust the device gain on the
Raspberry Pi audio settings down a little until the ranges are detectable by this app.

README:
The default pins set here are 22 and 25, GPO pins on the pi.
you can adjust these to your needs below in the NAMES section, also the thresholds for audio input.


This app was adapted from an example off of sounddevice documentation,
combined with GPIO to send trigger signals at set thresholds for 2 distinct
triggers. This enables for multiple tallies to be controlled from a single
mono input.
To adjust it, simply pass the tone signals through a fader and lower the gain
of the second channel, and output a mono channel to the mic input of the pi.

Make sure to have Matplotlib, numpy, sounddevice and RPi.GPIO libraries installed.

"""

import argparse
import queue
import sys
from matplotlib.animation import FuncAnimation
import matplotlib.pyplot as plt
import numpy as np
import sounddevice as sd
import RPi.GPIO as GPIO


#####   NAMES and THRESHOLDS
####################################################################################
####   right here, set threshold values and trigger names for visual reference  ####
name1 = "Camera 4"
name1threshold = 0.80  # best to set the max no more than .9, as input value max is 1.

name2 = "Camera 7"
name2threshold = 0.20  # represents -20 db for input, so adjust the gain level of this channel output to -20

off_threshold = 0.10  # lowest level, below this will turn them all off

pinone = 22
pintwo = 25

GPIO.setmode(GPIO.BCM)
GPIO.setup(pinone, GPIO.OUT)
GPIO.setup(pintwo, GPIO.OUT)


def liton(pin):
    GPIO.output(pin, GPIO.HIGH)
    return GPIO.input(pin)


def litoff(pin):
    GPIO.output(pin, GPIO.LOW)
    return GPIO.input(pin)


def int_or_str(text):
    """Helper function for argument parsing."""
    try:
        return int(text)
    except ValueError:
        return text


parser = argparse.ArgumentParser(add_help=False)
parser.add_argument(
    '-l', '--list-devices', action='store_true',
    help='show list of audio devices and exit')
args, remaining = parser.parse_known_args()
if args.list_devices:
    print(sd.query_devices())
    parser.exit(0)
parser = argparse.ArgumentParser(
    description=__doc__,
    formatter_class=argparse.RawDescriptionHelpFormatter,
    parents=[parser])
parser.add_argument(
    'channels', type=int, default=[1], nargs='*', metavar='CHANNEL',
    help='input channels to plot (default: the first)')
parser.add_argument(
    '-d', '--device', type=int_or_str,
    help='input device (numeric ID or substring)')
parser.add_argument(
    '-w', '--window', type=float, default=200, metavar='DURATION',
    help='visible time slot (default: %(default)s ms)')
parser.add_argument(
    '-i', '--interval', type=float, default=30,
    help='minimum time between plot updates (default: %(default)s ms)')
parser.add_argument(
    '-b', '--blocksize', type=int, help='block size (in samples)')
parser.add_argument(
    '-r', '--samplerate', type=float, help='sampling rate of audio device')
parser.add_argument(
    '-n', '--downsample', type=int, default=10, metavar='N',
    help='display every Nth sample (default: %(default)s)')
args = parser.parse_args(remaining)
if any(c < 1 for c in args.channels):
    parser.error('argument CHANNEL: must be >= 1')
mapping = [c - 1 for c in args.channels]  # Channel numbers start with 1
q = queue.Queue()


def audio_callback(indata, frames, time, status):
    """This is called (from a separate thread) for each audio block."""
    if status:
        print(status, file=sys.stderr)
    # Fancy indexing with mapping creates a (necessary!) copy:
    q.put(indata[::args.downsample, mapping])


def update_plot(frame):
    """This is called by matplotlib for each plot update.

    Typically, audio callbacks happen more frequently than plot updates,
    therefore the queue tends to contain multiple blocks of audio data.

    """
    global plotdata
    while True:
        try:
            data = q.get_nowait()
        except queue.Empty:
            break
        shift = len(data)
        # print('the data? ', data, end='\n')
        plotdata = np.roll(plotdata, -shift, axis=0)
        plotdata[-shift:, :] = data

        # this area, use plotdata to determine if GPI goes on or not
        themax = plotdata.max()
        pin = None

        # state of each tally to start:
        cam_a = 0
        cam_b = 0
        # set thresholds from here:
        if themax > name1threshold:
            cam_a = liton(pinone)
            cam_b = litoff(pintwo)
            print(f'{name1} on')
            
        elif themax > name2threshold:
            cam_b = liton(pintwo)
            cam_a = litoff(pinone)
            print(f'{name2} on')
            
        elif themax < off_threshold:
            litoff(pinone)
            litoff(pintwo)
            cam_a = 0
            tam_b = 0
            print('all off')

    for column, line in enumerate(lines):
        line.set_ydata(plotdata[:, column])
    return lines


try:
    if args.samplerate is None:
        device_info = sd.query_devices(args.device, 'input')
        args.samplerate = device_info['default_samplerate']

    length = int(args.window * args.samplerate / (1000 * args.downsample))
    plotdata = np.zeros((length, len(args.channels)))
        
    fig, ax = plt.subplots()
    lines = ax.plot(plotdata)
    if len(args.channels) > 1:
        ax.legend(['channel {}'.format(c) for c in args.channels],
                  loc='lower left', ncol=len(args.channels))
    ax.axis((0, len(plotdata), -1, 1))
    ax.set_yticks([0])
    ax.yaxis.grid(True)
    ax.tick_params(bottom=False, top=False, labelbottom=False,
                   right=False, left=False, labelleft=False)
    fig.tight_layout(pad=0)

    stream = sd.InputStream(
        device=args.device, channels=max(args.channels),
        samplerate=args.samplerate, callback=audio_callback)
    ani = FuncAnimation(fig, update_plot, interval=args.interval, blit=True)
    with stream:
        plt.show()
except Exception as e:
    parser.exit(type(e).__name__ + ': ' + str(e))

GPIO.cleanup()
