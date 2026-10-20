%% fft_square_accurate.m — Amplitude-accurate FFT (DC removed, Flattop, CG-corrected)
clear; clc;

% ---- Inputs ----
csvPath = 'data4.csv';
fs      = 3300;          % Hz
N       = 512;           % samples/FFT size
TOPK    = 10;            % how many peaks to report (before merging)
mergeHz = 10;            % +/- window in Hz for merging nearby peaks (display only)

% ---- Load ----
x = readmatrix(csvPath);
x = x(:);
if numel(x) < N
    error('CSV has %d samples; need %d.', numel(x), N);
end
x = x(1:N);                         % exactly 512 samples

% ---- Scale ALL samples before any further processing ----
scale_factor = 333/72;
x = x * scale_factor;

% ---- Basic stats on RAW data (with DC, as measured) ----
x_min  = min(x);
x_max  = max(x);
x_mean = mean(x);

% ---- Time vector (for plotting raw data) ----
t = (0:N-1).' / fs;

% ---- Remove DC (per your requirement: DC not important in FFT) ----
x_dc     = x_mean;
x_demean = x - x_dc;

% ---- Flattop window (5-term, amplitude-accurate) ----
% w(n) = a0 - a1*cos(2πn/(N-1)) + a2*cos(4πn/(N-1)) - a3*cos(6πn/(N-1)) + a4*cos(8πn/(N-1))
% Coeffs (Harris/ANSI): very close to MATLAB flattopwin
a0 = 1.0; a1 = 1.93; a2 = 1.29; a3 = 0.388; a4 = 0.032;
n   = (0:N-1).';
ang = 2*pi*n/(N-1);
w   = a0 ...
    - a1*cos(ang) ...
    + a2*cos(2*ang) ...
    - a3*cos(3*ang) ...
    + a4*cos(4*ang);

% Coherent gain (window average). This restores true amplitude.
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

if isempty(cand)
    warning('No peaks found above threshold %.3g.', th);
    fsorted    = [];
    as         = [];
    peaksTable = table();
else
    % Parabolic interpolation around each candidate (on linear magnitudes)
    % Returns sub-bin frequency and refined amplitude
    pb    = bins(cand);
    f_est = zeros(numel(pb),1);
    a_est = zeros(numel(pb),1);

    for k = 1:numel(pb)
        b  = pb(k);                   % 2..N/2
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

    % Sort by amplitude and keep TOPK (pre-merge)
    [as, ord] = sort(a_est, 'descend');
    fsorted   = f_est(ord);
    K         = min(TOPK, numel(as));
    as        = as(1:K);
    fsorted   = fsorted(1:K);

    % ---- Merge nearby peaks for DISPLAY ONLY (keep strongest amplitude) ----
    keep    = true(size(as));   % which peaks are still "alive"
    f_new   = zeros(size(as));
    a_new   = zeros(size(as));
    idx_new = 0;

    for i = 1:K
        if ~keep(i), continue; end

        % Start a new cluster around this peak
        idx_new = idx_new + 1;
        cluster_idx = i;          % indices in this cluster
        keep(i) = false;

        for j = i+1:K
            if keep(j) && abs(fsorted(j) - fsorted(i)) <= mergeHz
                cluster_idx(end+1) = j; %#ok<AGROW>
                keep(j) = false;
            end
        end

        % Amplitude = strongest bin in the cluster (no energy summing)
        [a_max, idx_local_max] = max(as(cluster_idx));
        a_new(idx_new) = a_max;

        % Frequency = frequency of strongest bin
        f_new(idx_new) = fsorted(cluster_idx(idx_local_max));
    end

    % Trim arrays to actual number of merged peaks
    fsorted = f_new(1:idx_new);
    as      = a_new(1:idx_new);

    % Resort merged peaks by amplitude (descending)
    [as, ord2] = sort(as, 'descend');
    fsorted    = fsorted(ord2);
    K          = numel(as);

    % ---- Optional: return table in workspace ----
    peaksTable = table(fsorted(:), as(:), ...
        'VariableNames', {'Frequency_Hz','Amplitude_raw'});
end

% ---- Plots ----
c = [0.15 0.61 0.22]; %dark green
% --- Time-domain plot (separate figure) ---
figure('Name','Time-Domain Waveforms of PWM-Modulated Lighting Panels','Position',[300 300 6000 500]);
plot(t, x, 'Color', c, 'LineWidth', 3); 
grid on;
xlim([0 0.05]);
xlabel('Time (s)', 'FontSize', 30, 'FontWeight', 'bold');
ylabel('Illuminance [lux](Measured)', 'FontSize', 30, 'FontWeight', 'bold');
title(sprintf('Time-Domain Waveforms of PWM-Modulated Lighting Panels'));

    % --- Tick styling ---
    ax = gca;
    ax.FontSize = 25;
    ax.FontWeight = 'bold';

% --- FFT / frequency-domain plot (separate figure) ---
figure('Name','Frequency domain','Position',[300 300 6000 500]);
stem(f, mag, 'filled','MarkerSize',3); 
hold on; grid on;

% % ---- Add virtual FFT bar (manual data point) ----
% x_manual = 135.350;   % Hz
% y_manual = 72.4467;    % amplitude
% 
% 
% stem(x_manual, y_manual, ...
%     'Color', [0 0.4470 0.7410], ...   % same MATLAB blue
%     'LineWidth', 1, ...
%     'Marker', 'o', ...
%     'MarkerSize', 5, ...
%     'MarkerFaceColor', [0 0.4470 0.7410]);


if ~isempty(as)
    plot(fsorted, as, 'o', 'MarkerSize',5, 'LineWidth',1); % highlight selected peaks
end
xlabel('Frequency (Hz)');
ylabel('Amplitude (raw units, peak)');
title(sprintf('Frequency-Domain Spectrum of PWM-Modulated Lighting Panels'));


% ---- Print results (exclude DC by design) ----
fprintf('fs = %.3f Hz, N = %d, bin width = %.6f Hz\n', fs, N, fs/N);
fprintf('RAW data stats (with DC):\n');
fprintf('   min   = %.6g\n', x_min);
fprintf('   max   = %.6g\n', x_max);
fprintf('   mean  = %.6g\n\n', x_mean);

fprintf('DC level (from time domain) used for de-meaning = %.6g (raw units)\n', x_dc);

if ~isempty(as)
    fprintf('\nTop %d merged spectral peaks (DC excluded):\n', K);
    fprintf('  #%2s  %12s  %14s\n', '', 'Frequency (Hz)', 'Amplitude (raw)');
    for i = 1:K
        fprintf('  %2d   %12.4f   %14.6g\n', i, fsorted(i), as(i));
    end
else
    fprintf('\nNo peaks above threshold; peaksTable is empty.\n');
end

disp('peaksTable (merged):');
disp(peaksTable);
