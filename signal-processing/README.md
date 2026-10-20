# MATLAB Signal Processing and Flicker Characterization

**Smart Indoor Lighting Control System · University of Tehran**

This section presents the MATLAB signal-processing work used to characterize measured light-intensity fluctuations and investigate **PWM modulation, spectral components, and flicker-related frequency behavior**. The analysis also supports the frequency-oriented calibration research conducted for the smart-lighting system.

## Processing approach

Measured light-sensor samples are examined in the **time domain** and transformed into the **frequency domain** using FFT. The MATLAB workflows include DC-offset removal, Hann or five-term Flattop windowing, single-sided spectrum calculation with coherent-gain compensation, spectral peak detection, and parabolic interpolation for refined peak-frequency estimates. Selected scripts also merge nearby detected peaks for reporting.

For a measured sequence `x[n]`, the main sequence is:

1. Subtract the mean to isolate the fluctuating component.
2. Apply the selected window to reduce spectral leakage.
3. Calculate the FFT and normalize the single-sided magnitude spectrum, accounting for window coherent gain.
4. Identify and report prominent frequency components and their amplitudes.

## MATLAB scripts

| Script | Function |
| --- | --- |
| [`fft_flattop_amplitude_corrected.m`](matlab/fft_flattop_amplitude_corrected.m) | Five-term Flattop-window FFT with sample scaling, corrected amplitudes, peak interpolation, and nearby-peak grouping. |
| [`fft_flattop_frequency_rescaled.m`](matlab/fft_flattop_frequency_rescaled.m) | Similar Flattop FFT with **intentional frequency/time-axis rescaling for presentation**. Rescaled axes are not an additional measured frequency. |
| [`fft_flattop_time_frequency.m`](matlab/fft_flattop_time_frequency.m) | Time-domain and single-sided frequency-domain plots, with prominent-peak analysis. |
| [`fft_hann_esp32_comparison.m`](matlab/fft_hann_esp32_comparison.m) | Hann-window FFT using magnitude scaling and peak interpolation for comparison with the ESP32 DSP processing pipeline. |

The four scripts retain their original computations and parameters. Only computer-specific CSV directory paths were replaced by relative CSV filenames (`data4.csv`, `data20.csv`, `data16.csv`, and `data5.csv`). Place the corresponding measurement files in the MATLAB working directory, or point each script to their actual location.

## Experimental figures

### Measured illuminance signal

![Measured illuminance in the time domain](images/measured_illuminance_time_domain.png)

**Time-domain sensor output:** variations in recorded illuminance during the lighting experiment.

### FFT of the measured illuminance

![Frequency spectrum of measured illuminance](images/measured_illuminance_fft.png)

**Frequency-domain analysis:** spectral peaks extracted from the measured light signal.

### PWM-modulated light — time domain

![PWM light waveform in time domain](images/pwm_time_domain.png)

**Time-domain waveform:** measured illuminance variation from PWM-modulated lighting panels.

### PWM-modulated light — frequency domain

![PWM light frequency spectrum](images/pwm_fft_spectrum.png)

**FFT spectrum:** dominant modulation frequency and additional spectral components; peak frequency and amplitude are annotated in the plot.

### Additional PWM waveform example

![Waveform at 90 percent duty and 100 Hz](images/pwm_90percent_waveform.png)

**Additional measured waveform:** lighting panel at **90% duty cycle**, **100 Hz** nominal modulation frequency, and **2 m** measurement distance, as labeled in the original figure.

## Related research

The mathematical procedure and frequency-oriented calibration methodology are discussed in the conference paper **“On-the-Fly Frequency-Oriented Calibration for Real-Time, Power-Efficient, and Dynamic Control of Smart Lighting Systems”** ([DOI: 10.1109/ICEE70628.2026.11710520](https://doi.org/10.1109/ICEE70628.2026.11710520)).

For the central control application, see [`control-and-optimization/`](../control-and-optimization/). Hardware experiments and the flicker measurement module are described in [`hardware/`](../hardware/).
