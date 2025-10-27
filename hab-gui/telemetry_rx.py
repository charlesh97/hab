"""
Telemetry Receiver using GNU Radio

This module handles the reception and processing of telemetry data
using GNU Radio blocks.
"""

import threading
import time
import numpy as np
from gnuradio import gr, blocks, fft
from gnuradio.fft import window
try:
    from gnuradio import analog
except ImportError:
    analog = None


class TelemetryReceiver(gr.top_block):
    """
    GNU Radio flowgraph for receiving telemetry data
    """

    def __init__(self, callback_func, spectrum_callback_func=None):
        gr.top_block.__init__(self, "Telemetry Receiver")

        self.callback_func = callback_func
        self.spectrum_callback_func = spectrum_callback_func
        self.running = False
        self.thread = None

        ##################################################
        # Variables
        ##################################################
        self.samp_rate = samp_rate = 2e6
        self.center_freq = center_freq = 434e6
        self.fft_size = 1024

        ##################################################
        # Blocks for Spectrum Analyzer
        ##################################################
        
        # Stream to vector for FFT
        self.stream_to_vector = blocks.stream_to_vector(gr.sizeof_gr_complex, self.fft_size)
        
        # FFT block
        self.fft_block = fft.fft_vcc(self.fft_size, True, window.blackmanharris(self.fft_size), True, 1)
        
        # Complex to magnitude squared (power)
        self.c2mag = blocks.complex_to_mag_squared(self.fft_size)
        
        # Vector sink to capture FFT data
        self.vector_sink = blocks.vector_sink_f(self.fft_size)
        
        ##################################################
        # TODO: Add your telemetry processing blocks here
        ##################################################
        # Example structure:
        # 
        # self.source = soapy.source(...)
        # self.demodulator = digital.fsk_demod(...)
        # self.decoder = digital.packet_decoder(...)
        # 
        # Connect blocks for telemetry:
        # self.connect((self.source, 0), (self.demodulator, 0))
        # self.connect((self.demodulator, 0), (self.decoder, 0))
        
        # For now, create a simple message debug sink as placeholder
        # This will be replaced with actual telemetry processing blocks
        
        # Create a message sink that will receive telemetry packets
        self.msg_sink = blocks.message_debug()
        
        # You'll connect your telemetry decoder output to this sink
        # Example:
        # self.msg_connect((self.packet_decoder, 'out'), (self, 'telemetry'))
        
        ##################################################
        # Connect FFT blocks for spectrum analyzer
        ##################################################
        # NOTE: Once you add your source block, connect it to the FFT chain:
        # self.connect((self.source, 0), (self.stream_to_vector, 0))
        # self.connect((self.stream_to_vector, 0), (self.fft_block, 0))
        # self.connect((self.fft_block, 0), (self.c2mag, 0))
        # self.connect((self.c2mag, 0), (self.vector_sink, 0))

    def start_rx(self):
        """Start the receiver"""
        if not self.running:
            self.start()
            self.running = True
            # Start a thread to poll for messages
            self.thread = threading.Thread(target=self._message_poll_loop, daemon=True)
            self.thread.start()

    def stop_rx(self):
        """Stop the receiver"""
        if self.running:
            self.running = False
            self.stop()
            self.wait()
            if self.thread:
                self.thread.join(timeout=2.0)

    def _message_poll_loop(self):
        """
        Poll for received messages and call the callback function
        This runs in a separate thread
        """
        while self.running:
            # Poll for spectrum data
            if self.spectrum_callback_func:
                self._update_spectrum()
            
            # TODO: Implement message polling from GNU Radio message queue for telemetry
            # For now, simulate receiving data periodically
            time.sleep(0.1)  # 10 Hz update rate
            
            # When you receive actual telemetry data, call:
            # self.callback_func(received_data_bytes)
            
            # Example placeholder:
            # received_data = b"Example telemetry packet"
            # self.callback_func(received_data)

    def _update_spectrum(self):
        """Extract FFT data and call spectrum callback"""
        try:
            # Get data from vector sink
            data = np.array(self.vector_sink.data())
            
            if len(data) >= self.fft_size:
                # Get the most recent FFT frame
                fft_data = data[-self.fft_size:]
                
                # Convert to dB
                power_db = 10.0 * np.log10(fft_data + 1e-10)  # Add small value to avoid log(0)
                
                # FFT shift to center DC
                power_db = np.fft.fftshift(power_db)
                
                # Generate frequency bins
                freq_bins = np.fft.fftshift(np.fft.fftfreq(self.fft_size, 1.0/self.samp_rate))
                frequencies = self.center_freq + freq_bins
                
                # Call the callback with frequency and power data
                self.spectrum_callback_func(frequencies, power_db)
        except Exception as e:
            pass  # Silently ignore errors to avoid flooding console

    def set_frequency(self, freq_hz):
        """Set center frequency"""
        self.center_freq = freq_hz
        # TODO: Update your source block frequency
        # Example: self.source.set_frequency(freq_hz)

    def set_sample_rate(self, rate_hz):
        """Set sample rate"""
        self.samp_rate = rate_hz
        # TODO: Update your source block sample rate
        # Example: self.source.set_sample_rate(rate_hz)

    def set_gain(self, gain_name, gain_value):
        """Set gain value"""
        # TODO: Update your source block gain
        # Example: self.source.set_gain(gain_value, gain_name)
        pass


# Standalone interface for use with the GUI
class TelemetryReceiverInterface:
    """
    Wrapper interface for the telemetry receiver that can be used
    independently from the GNU Radio top block
    """

    def __init__(self, on_packet_received, on_spectrum_received=None):
        self.on_packet_received = on_packet_received
        self.on_spectrum_received = on_spectrum_received
        self.flowgraph = None

    def start(self):
        """Start telemetry reception"""
        if self.flowgraph is None:
            self.flowgraph = TelemetryReceiver(
                self._handle_packet,
                self._handle_spectrum if self.on_spectrum_received else None
            )
        self.flowgraph.start_rx()

    def stop(self):
        """Stop telemetry reception"""
        if self.flowgraph:
            self.flowgraph.stop_rx()

    def _handle_packet(self, data: bytes):
        """Internal packet handler that calls the user callback"""
        if self.on_packet_received:
            self.on_packet_received(data)

    def _handle_spectrum(self, frequencies: np.ndarray, power_db: np.ndarray):
        """Internal spectrum handler that calls the user callback"""
        if self.on_spectrum_received:
            self.on_spectrum_received(frequencies, power_db)

    def update_parameters(self, frequency=None, sample_rate=None, gains=None):
        """Update receiver parameters"""
        if self.flowgraph:
            if frequency:
                self.flowgraph.set_frequency(frequency)
            if sample_rate:
                self.flowgraph.set_sample_rate(sample_rate)
            if gains:
                for gain_name, gain_value in gains.items():
                    self.flowgraph.set_gain(gain_name, gain_value)


def packet_processing(data: bytes) -> str:
    """
    Process received telemetry packet
    
    Args:
        data: Raw packet data bytes
        
    Returns:
        Processed string representation for display
    """
    # TODO: Implement actual packet processing
    # For now, just return hex representation
    return f"Packet ({len(data)} bytes): {data.hex()}"


if __name__ == "__main__":
    # Test the receiver
    def test_callback(data):
        print(f"Received: {packet_processing(data)}")

    rx = TelemetryReceiverInterface(test_callback)
    print("Starting receiver...")
    rx.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping receiver...")
        rx.stop()

