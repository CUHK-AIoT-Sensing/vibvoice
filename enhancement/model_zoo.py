import torch
import numpy as np
from evaluation import batch_pesq, SI_SDR, lsd, STOI, eval_ASR
import torch.nn.functional as F
from scipy import signal
from audio_zen.acoustics.mask import build_complex_ideal_ratio_mask, decompress_cIRM
from audio_zen.acoustics.feature import drop_band
from speechbrain.pretrained import EncoderDecoderASR
'''
This script contains 4 model's training and test due to their large differences (for concise)
1. FullSubNet, LSTM, spectrogram magnitude -> cIRM
2. SEANet, GAN, time-domain, encoder-decoder,
3. A2Net (VibVoice), spectrogram magnitude -> spectrogram magnitude
4. Conformer, GAN, spectrogram real+imag -> real+imag
'''
seg_len_mic = 640
overlap_mic = 320
seg_len_imu = 64
overlap_imu = 32
rate_mic = 16000
rate_imu = 1600
freq_bin_high = 8 * int(rate_imu / rate_mic * int(seg_len_mic / 2)) + 1

# Uncomment for using another pre-trained model
# asr_model = EncoderDecoderASR.from_hparams(source="speechbrain/asr-transformer-transformerlm-librispeech",
#                                            savedir="pretrained_models/asr-transformer-transformerlm-librispeech",
#                                            run_opts={"device": "cuda"})
def eval(clean, predict, text=None):
    metric1 = batch_pesq(clean, predict)
    metric2 = SI_SDR(clean, predict)
    metric3 = lsd(clean, predict)
    #metric4 = STOI(clean, predict)
    metrics = [metric1, metric2, metric3]
    # if text is not None:
    #     wer_clean, wer_noisy = eval_ASR(clean, predict, text, asr_model)
    #     metrics.append(wer_clean)
    #     metrics.append(wer_noisy)
    return np.stack(metrics, axis=1)
def Spectral_Loss(x_mag, y_mag):
    """Calculate forward propagation.
          Args:
              x_mag (Tensor): Magnitude spectrogram of predicted signal (B, #frames, #freq_bins).
              y_mag (Tensor): Magnitude spectrogram of groundtruth signal (B, #frames, #freq_bins).
          Returns:
              Tensor: Spectral convergence loss value.
          """
    x_mag = torch.clamp(x_mag, min=1e-7)
    y_mag = torch.clamp(y_mag, min=1e-7)
    spectral_convergenge_loss = torch.norm(y_mag - x_mag, p="fro") / torch.norm(y_mag, p="fro")
    log_stft_magnitude = F.l1_loss(torch.log(y_mag), torch.log(x_mag))
    return 0.5 * spectral_convergenge_loss + 0.5 * log_stft_magnitude

def train_SEANet(model, acc, noise, clean, optimizer, optimizer_disc=None, discriminator=None, device='cuda'):
    predict1, predict2 = model(acc.to(device=device, dtype=torch.float), noise.to(device=device, dtype=torch.float))
    # generator
    optimizer.zero_grad()
    disc_fake = discriminator(predict1)
    disc_real = discriminator(clean.to(device=device, dtype=torch.float))
    (feats_fake, score_fake), (feats_real, _) = (disc_fake, disc_real)
    loss = torch.mean(torch.sum(torch.pow(score_fake - 1.0, 2), dim=[1, 2]))
    for feat_f, feat_r in zip(feats_fake, feats_real):
        loss += 100 * torch.mean(torch.abs(feat_f - feat_r))
    loss.backward()
    optimizer.step()

    # discriminator
    optimizer_disc.zero_grad()
    disc_fake = discriminator(predict1.detach())
    disc_real = discriminator(clean.to(device=device, dtype=torch.float))
    (_, score_fake), (_, score_real) = (disc_fake, disc_real)
    discrim_loss = torch.mean(torch.sum(torch.pow(score_real - 1.0, 2), dim=[1, 2]))
    discrim_loss += torch.mean(torch.sum(torch.pow(score_fake, 2), dim=[1, 2]))
    discrim_loss.backward()
    optimizer_disc.step()
    return loss.item(), discrim_loss.item()
def test_SEANet(model, acc, noise, clean, device='cuda'):
    predict1, predict2 = model(acc.to(device=device, dtype=torch.float), noise.to(device=device, dtype=torch.float))
    clean = clean.squeeze(1).numpy()
    predict = predict1.cpu().numpy()
    return eval(clean, predict)

def train_vibvoice(model, acc, noise, clean, optimizer, device='cuda'):
    acc = acc.to(device=device, dtype=torch.float)
    noise_mag = noise.abs().to(device=device, dtype=torch.float)
    clean_mag = clean.abs().to(device=device, dtype=torch.float)
    optimizer.zero_grad()
    # VibVoice
    predict1, predict2 = model(acc, noise_mag)
    loss = Spectral_Loss(predict1, clean_mag)
    loss += F.mse_loss(predict2, clean_mag[:, :, :32, :])
    loss.backward()
    optimizer.step()
    return loss.item()
def test_vibvoice(model, acc, noise, clean, device='cuda', text=None):
    acc = acc.to(device=device, dtype=torch.float)
    noise_mag = torch.abs(noise).to(device=device, dtype=torch.float)
    noise_pha = torch.angle(noise).to(device=device, dtype=torch.float)
    clean = clean.to(device=device).squeeze(1)

    predict1, _ = model(acc, noise_mag)
    predict1 = torch.exp(1j * noise_pha) * predict1
    predict1 = predict1.squeeze(1)

    predict = predict1.cpu().numpy()
    clean = clean.cpu().numpy()

    predict = np.pad(predict, ((0, 0), (1, int(seg_len_mic / 2) + 1 - freq_bin_high), (1, 0)))
    predict = signal.istft(predict, rate_mic, nperseg=seg_len_mic, noverlap=overlap_mic)[-1]
    clean = np.pad(clean, ((0, 0), (1, int(seg_len_mic / 2) + 1 - freq_bin_high), (1, 0)))
    clean = signal.istft(clean, rate_mic, nperseg=seg_len_mic, noverlap=overlap_mic)[-1]
    return eval(clean, predict, text=text)

def train_fullsubnet(model, acc, noise, clean, optimizer, device='cuda'):
    noise_mag = noise.abs().to(device=device, dtype=torch.float)
    optimizer.zero_grad()
    cIRM = build_complex_ideal_ratio_mask(noise.real, noise.imag, clean.real, clean.imag)
    cIRM = cIRM.to(device=device, dtype=torch.float)
    cIRM = drop_band(cIRM, model.module.num_groups_in_drop_band)
    predict1 = model(noise_mag)
    loss = F.l1_loss(predict1, cIRM)
    loss.backward()
    optimizer.step()
    return loss.item()
def test_fullsubnet(model, acc, noise, clean, device='cuda'):
    noise_mag = torch.abs(noise).to(device=device, dtype=torch.float)
    noise_real = noise.real.to(device=device, dtype=torch.float)
    noise_imag = noise.imag.to(device=device, dtype=torch.float)
    clean = clean.to(device=device).squeeze(1)

    predict1 = model(noise_mag)
    cRM = decompress_cIRM(predict1.permute(0, 2, 3, 1))
    enhanced_real = cRM[..., 0] * noise_real.squeeze(1) - cRM[..., 1] * noise_imag.squeeze(1)
    enhanced_imag = cRM[..., 1] * noise_real.squeeze(1) + cRM[..., 0] * noise_imag.squeeze(1)
    predict1 = torch.complex(enhanced_real, enhanced_imag)
    predict = predict1.cpu().numpy()
    predict = np.pad(predict, ((0, 0), (1, int(seg_len_mic / 2) + 1 - freq_bin_high), (1, 0)))
    predict = signal.istft(predict, rate_mic, nperseg=seg_len_mic, noverlap=overlap_mic)[-1]

    clean = clean.cpu().numpy()
    clean = np.pad(clean, ((0, 0), (1, int(seg_len_mic / 2) + 1 - freq_bin_high), (1, 0)))
    clean = signal.istft(clean, rate_mic, nperseg=seg_len_mic, noverlap=overlap_mic)[-1]
    return eval(clean, predict)

def train_conformer(model, acc, noise, clean, optimizer, optimizer_disc=None, discriminator=None, device='cuda'):

    clean_mag = clean.abs().to(device=device, dtype=torch.float)
    # predict real and imag - conformer
    optimizer.zero_grad()
    noisy_spec = torch.stack([noise.real, noise.imag], 1).to(device=device, dtype=torch.float).permute(0, 1, 3, 2)
    clean_real, clean_imag = clean.real.to(device=device, dtype=torch.float), clean.imag.to(device=device, dtype=torch.float)
    est_real, est_imag = model(noisy_spec)
    est_mag = torch.sqrt(est_real ** 2 + est_imag ** 2)
    loss = 0.9 * F.mse_loss(est_mag, clean_mag) + 0.1 * F.mse_loss(est_real, clean_real) + F.mse_loss(est_imag, clean_imag)

    # adversarial training
    BATCH_SIZE = noise.shape[0]
    one_labels = torch.ones(BATCH_SIZE).cuda()
    predict_fake_metric = discriminator(clean_mag, est_mag)
    gen_loss_GAN = F.mse_loss(predict_fake_metric.flatten(), one_labels.float())
    loss += 0.1 * gen_loss_GAN
    loss.backward()
    optimizer.step()

    # discriminator loss
    optimizer_disc.zero_grad()
    predict = torch.complex(est_real, est_imag)
    predict_audio = predict.detach().cpu().numpy()
    predict_audio = np.pad(predict_audio, ((0, 0), (0, 0), (1, int(seg_len_mic / 2) + 1 - freq_bin_high), (1, 0)))
    predict_audio = signal.istft(predict_audio, rate_mic, nperseg=seg_len_mic, noverlap=overlap_mic)[-1]

    clean_audio = np.pad(clean, ((0, 0), (0, 0), (1, int(seg_len_mic / 2) + 1 - freq_bin_high), (1, 0)))
    clean_audio = signal.istft(clean_audio, rate_mic, nperseg=seg_len_mic, noverlap=overlap_mic)[-1]

    pesq_score = discriminator.batch_pesq(clean_audio, predict_audio)
    # The calculation of PESQ can be None due to silent part
    if pesq_score is not None:
        optimizer_disc.zero_grad()
        predict_enhance_metric = discriminator(clean_mag, predict.detach())
        predict_max_metric = discriminator(clean_mag, clean_mag)
        discrim_loss = F.mse_loss(predict_max_metric.flatten(), one_labels) + \
                       F.mse_loss(predict_enhance_metric.flatten(), pesq_score)
        discrim_loss.backward()
        optimizer_disc.step()
    else:
        discrim_loss = torch.tensor([0.])
    return loss.item(), discrim_loss.item()
def test_conformer(model, acc, noise, clean, device='cuda'):
    # predict real and imag - conformer
    noisy_spec = torch.stack([noise.real, noise.imag], 1).to(device=device, dtype=torch.float).permute(0, 1, 3, 2)
    est_real, est_imag = model(noisy_spec)
    predict = torch.complex(est_real, est_imag)

    predict = predict.cpu().numpy()
    clean = clean.cpu().numpy()

    predict = np.pad(predict, ((0, 0), (1, int(seg_len_mic / 2) + 1 - freq_bin_high), (1, 0)))
    predict = signal.istft(predict, rate_mic, nperseg=seg_len_mic, noverlap=overlap_mic)[-1]

    clean = np.pad(clean, ((0, 0), (1, int(seg_len_mic / 2) + 1 - freq_bin_high), (1, 0)))
    clean = signal.istft(clean, rate_mic, nperseg=seg_len_mic, noverlap=overlap_mic)[-1]
    return eval(clean, predict)