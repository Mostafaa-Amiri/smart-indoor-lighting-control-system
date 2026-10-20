%% compare_fft.m — Mirror of ESP32 esp-dsp pipeline in MATLAB
clear; clc;

% ---- User settings (match ESP code) ----
FS   = 3300.0;       % sampling rate [Hz]
N    = 512;          % FFT size
TOPK = 5;            % number of peaks to print
csv_path = 'data5.csv';

% ---- Load CSV (single column of integers is fine) ----
x_raw = readmatrix(csv_path);
x_raw = x_raw(:);     % make column

% Use first N samples; zero-pad if fewer
if numel(x_raw) < N
    x_raw(end+1:N,1) = 0;
elseif numel(x_raw) > N
    x_raw = x_raw(1:N);
end

% ---- DC removal (same as ESP) ----
x_mean = mean(x_raw);
x_demean = x_raw - x_mean;

% ---- Hann window identical to your C hann(i,N) = 0.5*(1 - cos(2*pi*i/(N-1))) ----
n = (0:N-1).';
w = 0.5*(1 - cos(2*pi*n/(N-1)));          % symmetric Hann (same as your code)
cg = mean(w);                              % coherent gain for amplitude compensation (~0.5)

xw = x_demean .* w;                        % windowed signal in RAW counts

% ---- FFT & magnitude scaling (mirror C scaling) ----
X  = fft(xw, N);
% We’ll form positive spectrum bins 0..N/2-1 (MATLAB indices 1..N/2)
pos_bins = 1:(N/2);
Re = real(X(pos_bins));
Im = imag(X(pos_bins));
mag = hypot(Re, Im);

scale = (2.0 / N) / cg;                    % identical to your C: (2/N)/cg
mag = mag * scale;                         % peak amplitude in raw counts
mag = mag / 1.8;               % global scaling (e.g., 450 → 250)

% ---- Frequency vector for those bins ----
f = (pos_bins - 1) * (FS / N);             % Hz, 0..(N/2-1)*FS/N

% ---- Find Top-K peaks (ignore DC bin 0) ----
bins = numel(pos_bins);                    % N/2
search_bins = 2:bins;                      % skip DC (bin 1 in MATLAB indexing)
[sorted_vals, sorted_idx_rel] = maxk(mag(search_bins), TOPK);
peak_bins = search_bins(sorted_idx_rel);   % MATLAB-bin indices 1..N/2

% ---- Parabolic interpolation around each peak (like in your helper) ----
% Works on linear magnitudes (same as your C parabolic_peak)
fprintf('FS=%.3f Hz, N=%d, resolution=%.6f Hz/bin\n', FS, N, FS/N);
for i = 1:TOPK
    b = peak_bins(i);                      % MATLAB index of the peak (>=2 and <= N/2-1 ideally)
    if b <= 1 || b >= bins                 % guard rails
        delta = 0.0;
        amp_i = mag(b);
    else
        ml = mag(b-1); mc = mag(b); mr = mag(b+1);
        denom = (ml - 2*mc + mr);
        if abs(denom) > 1e-12
            delta = 0.5 * (ml - mr) / denom; % fractional bin offset in [-0.5,+0.5]
        else
            delta = 0.0;
        end
        % amplitude at vertex of fitted parabola
        amp_i = mc - 0.25*(ml - mr)*delta;
        % clamp delta for sanity
        delta = max(min(delta, 0.5), -0.5);
    end

    % Convert to Hz (remember MATLAB indexing: f(b) corresponds to bin (b-1))
    f_i   = ((b - 1 + delta) * FS) / N;    % Hz
    peak  = amp_i;                          % peak amplitude [raw counts]
    rms_t = peak / sqrt(2);                 % RMS for pure tone
    p2p   = 2*peak;                         % peak-to-peak

    fprintf('%d) %8.2f Hz | peak=%8.3f counts  (bin %d %+0.3f)  [rms=%.3f, p2p=%.3f]\n', ...
        i, f_i, peak, (b-1), delta, rms_t, p2p);
end

% ---- (Optional) Quick plot to visually compare spectrum ----
figure; 
plot(f, mag, 'LineWidth', 1);
xlabel('Frequency (Hz)'); ylabel('Amplitude (counts, peak)');
title(sprintf('Spectrum (FS=%.0f Hz, N=%d, Hann, scaled like ESP)', FS, N));
grid on;
