%% fft_square_accurate.m — Amplitude-accurate FFT (DC removed, Flattop, CG-corrected)
clear; clc;

% ---- Inputs ----
csvPath = 'data16.csv';
fs      = 3300;          % Hz
N       = 512;           % samples/FFT size
TOPK    = 10;            % how many peaks to report (excluding DC)

% ---- Load ----
x = readmatrix(csvPath);
x = x(:);
if numel(x) < N, error('CSV has %d samples; need %d.', numel(x), N); end
x = x(1:N);                         % exactly 512 samples

% ---- Time vector (for plotting raw data) ----
t = (0:N-1).' / fs;

% ---- Remove DC (per your requirement: DC not important, do NOT mix with amps) ----
x_dc   = mean(x);
x_demean = x - x_dc;

% ---- Flattop window (5-term, amplitude-accurate) ----
% w(n) = a0 - a1*cos(2πn/(N-1)) + a2*cos(4πn/(N-1)) - a3*cos(6πn/(N-1)) + a4*cos(8πn/(N-1))
% Coeffs (Harris/ANSI): very close to MATLAB flattopwin
a0=1.0; a1=1.93; a2=1.29; a3=0.388; a4=0.032;
n = (0:N-1).';
ang = 2*pi*n/(N-1);
w = a0 ...
  - a1*cos(ang) ...
  + a2*cos(2*ang) ...
  - a3*cos(3*ang) ...
  + a4*cos(4*ang);

% Coherent gain (window average). This is NOT a "random gain"—it restores true amplitude.
cg = mean(w);

% ---- Window, FFT, amplitude scaling to raw units (peak) ----
xw = x_demean .* w;
X  = fft(xw, N);

% Use bins 0..N/2 (MATLAB indices 1..N/2+1). We’ll EXCLUDE DC and Nyquist from peak search.
pos = 1:(N/2+1);
mag = abs(X(pos));

% Scale to single-sided peak amplitude in raw units:
% - divide by N (DFT normalization)
% - convert two-sided -> single-sided: multiply non-DC/non-Nyquist bins by 2
% - divide by coherent gain of window (restores true peak for off-bin tones)
scale = 1/N;
mag(2:end-1) = mag(2:end-1) * 2;     % single-sided
mag = mag * (scale / cg);            % CG compensation => amplitudes in raw units (peak)

% Frequency axis
f = fs*(pos-1)/N;                    % 0 .. fs/2

% ---- Peak picking (exclude DC bin and Nyquist bin from search) ----
search_lo = 2;                % skip DC (bin 0)
search_hi = (N/2);            % skip Nyquist (last index = N/2+1)
bins = search_lo:search_hi;

% Basic prominence threshold (auto): small fraction of the max non-DC bin
th = 0.02 * max(mag(bins));   % 2% of max; tweak if you want more/fewer peaks
cand = find(mag(bins) >= th);

% Parabolic interpolation around each candidate (on linear magnitudes)
% Returns sub-bin frequency and refined amplitude
pb  = bins(cand);
f_est = zeros(numel(pb),1);
a_est = zeros(numel(pb),1);

for k = 1:numel(pb)
    b = pb(k);                   % 2..N/2
    ml = mag(b-1); mc = mag(b); mr = mag(b+1);
    denom = (ml - 2*mc + mr);
    if b<=1 || b>=(N/2) || abs(denom)<1e-15
        delta = 0;               % no interpolation at boundaries or flat
        a_vtx = mc;
    else
        delta = 0.5*(ml - mr)/denom;   % in [-0.5, 0.5]
        delta = max(min(delta,0.5),-0.5);
        a_vtx = mc - 0.25*(ml - mr)*delta; % vertex magnitude
    end
    f_est(k) = ( (b-1) + delta ) * fs / N;   % Hz (bin index is (b-1))
    a_est(k) = a_vtx;                        % peak amplitude (raw units)
end

% Sort by amplitude and keep TOPK
[as, ord] = sort(a_est, 'descend');
fsorted   = f_est(ord);
K = min(TOPK, numel(as));
as = as(1:K); fsorted = fsorted(1:K);

% ---- Plots ----
figure('Name','Time & Frequency (Amplitude-accurate)','Position',[80 80 1150 430]);

subplot(1,2,1);
plot(t, x, 'LineWidth', 1);
grid on; xlabel('Time (s)'); ylabel('Amplitude (raw units)');
title('Time Domain (raw, DC present)');

subplot(1,2,2);
stem(f, mag, 'filled','MarkerSize',3); hold on; grid on;
plot(fsorted, as, 'o', 'MarkerSize',5, 'LineWidth',1); % highlight selected peaks
xlabel('Frequency (Hz)'); ylabel('Amplitude (raw units, peak)');
title(sprintf('Single-Sided Spectrum (DC removed before FFT) — fs=%g Hz, N=%d', fs, N));

% ---- Print results (exclude DC by design) ----
fprintf('fs=%.3f Hz, N=%d, bin width=%.6f Hz\n', fs, N, fs/N);
fprintf('DC level (from time domain) = %.6g (raw units) — not included in peaks\n', x_dc);
fprintf('\nTop %d spectral peaks (DC excluded):\n', K);
fprintf('  #%2s  %12s  %14s\n', '', 'Frequency (Hz)', 'Amplitude (raw)');
for i = 1:K
    fprintf('  %2d   %12.4f   %14.6g\n', i, fsorted(i), as(i));
end

% ---- Optional: return table in workspace
peaksTable = table(fsorted, as, 'VariableNames', {'Frequency_Hz','Amplitude_raw'});
disp(peaksTable);
