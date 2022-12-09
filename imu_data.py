import os
import scipy.signal as signal
import scipy.interpolate as interpolate
import numpy as np
from scipy.spatial.transform import Rotation as R
import matplotlib.pyplot as plt
import librosa

rate_imu = 1600

def read_data(file, seg_len=256, overlap=224, rate=1600, mfcc=False, filter=True):
    fileobject = open(file, 'r')
    lines = fileobject.readlines()
    data = np.zeros((len(lines), 4))
    for i in range(len(lines)):
        line = lines[i].split(' ')
        data[i, :] = [float(item) for item in line]
    data[:, :-1] /= 2**14
    if filter:
        b, a = signal.butter(4, 10, 'highpass', fs=rate)
        data[:, :3] = signal.filtfilt(b, a, data[:, :3], axis=0)
        data[:, :3] = np.clip(data[:, :3], -0.05, 0.05)
    if mfcc:
        Zxx = []
        for i in range(3):
            Zxx.append(librosa.feature.melspectrogram(data[:, i], sr=rate, n_fft=seg_len, hop_length=seg_len-overlap, power=1))
        Zxx = np.array(Zxx)
        Zxx = np.linalg.norm(Zxx, axis=0)
    else:
        Zxx = signal.stft(data[:, :3], nperseg=seg_len, noverlap=overlap, fs=rate, axis=0)[-1]
        Zxx = np.linalg.norm(np.abs(Zxx), axis=1)
    return data, Zxx
def calibrate(file, T, shift):
    data = np.loadtxt(file)
    timestamp = data[:, -1]
    # data = data[:, :3] / 2 ** 14
    # data = data - np.mean(data, axis=0)
    data = data[:, :3]
    f = interpolate.interp1d(timestamp - timestamp[0], data, axis=0, kind='nearest')
    t = min((timestamp[-1] - timestamp[0]), T)
    num_sample = int(T * rate_imu)
    data = np.zeros((num_sample, 3))
    xnew = np.linspace(0, t, num_sample)
    data[shift:num_sample, :] = f(xnew)[:-shift, :]
    return data

if __name__ == "__main__":
    directory = 'dataset/positions/glasses'
    kinds = 3
    file_list = os.listdir(directory)
    file_list = sorted(file_list)
    N = len(file_list)
    N = int(N / kinds)
    imu1 = file_list[: N]
    imu2 = file_list[N: 2 * N]
    gt = file_list[2 * N: 3 * N]
    wav = file_list[3 * N:]
    for f1, f2 in zip(imu1, imu2):
        data1, Zxx1 = read_data(os.path.join(directory, f1))
        data2, Zxx2 = read_data(os.path.join(directory, f2))
        fig, axs = plt.subplots(2, 1)
        axs[0].imshow(Zxx1)
        axs[1].imshow(Zxx2)
        plt.show()

