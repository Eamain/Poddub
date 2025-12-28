
// import lamejs from 'lamejs'; // Loaded via global script in index.html

/**
 * Converts a Blob/File object to a Base64 string.
 */
export const blobToBase64 = (blob: Blob): Promise<string> => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.readAsDataURL(blob);
    reader.onload = () => {
      const result = reader.result as string;
      // Remove data URL prefix (e.g., "data:audio/mp3;base64,")
      const base64 = result.split(',')[1];
      resolve(base64);
    };
    reader.onerror = (error) => reject(error);
  });
};

// Deprecated alias for compatibility, uses the same logic
export const fileToBase64 = blobToBase64;

/**
 * Decodes a Base64 string to a Uint8Array.
 */
export function decodeBase64ToArray(base64: string): Uint8Array {
  const binaryString = atob(base64);
  const len = binaryString.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return bytes;
}

/**
 * Decodes raw PCM data from Gemini into an AudioBuffer.
 * Note: Gemini TTS typically returns 24kHz raw PCM.
 */
export async function decodeAudioData(
  data: Uint8Array,
  ctx: AudioContext,
  sampleRate: number = 24000,
  numChannels: number = 1
): Promise<AudioBuffer> {
  // Convert Uint8Array to Int16Array (PCM 16-bit)
  const dataInt16 = new Int16Array(data.buffer);
  const frameCount = dataInt16.length / numChannels;
  const buffer = ctx.createBuffer(numChannels, frameCount, sampleRate);

  for (let channel = 0; channel < numChannels; channel++) {
    const channelData = buffer.getChannelData(channel);
    for (let i = 0; i < frameCount; i++) {
      // Normalize Int16 to Float32 range [-1.0, 1.0]
      channelData[i] = dataInt16[i * numChannels + channel] / 32768.0;
    }
  }
  return buffer;
}

/**
 * Concatenates a list of Uint8Array (raw PCM bytes) into a single array.
 */
export function concatenatePCMData(arrays: Uint8Array[]): Uint8Array {
  // Calculate total length
  let totalLength = 0;
  for (const arr of arrays) {
    totalLength += arr.length;
  }

  const result = new Uint8Array(totalLength);
  let offset = 0;
  for (const arr of arrays) {
    result.set(arr, offset);
    offset += arr.length;
  }
  return result;
}

/**
 * Helper to convert Float32 AudioBuffer data to Int16 (required for WAV/MP3 encoding)
 */
function floatTo16BitPCM(input: Float32Array): Int16Array {
  const output = new Int16Array(input.length);
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]));
    output[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
  }
  return output;
}

/**
 * Encodes an AudioBuffer to an MP3 Blob using lamejs.
 */
/**
 * Encodes an AudioBuffer to an MP3 Blob using lamejs.
 * NOW ASYNC to prevent UI freeze on large files.
 */
export async function encodeMP3(buffer: AudioBuffer, kbps: number = 128, onProgress?: (percent: number) => void): Promise<Blob> {
  try {
    const channels = buffer.numberOfChannels;
    const sampleRate = buffer.sampleRate;

    // @ts-ignore
    const lib = window.lamejs;

    if (!lib || !lib.Mp3Encoder) {
      throw new Error("Lamejs library not loaded globally.");
    }

    const Mp3Encoder = lib.Mp3Encoder;

    // Instantiate Encoder
    // @ts-ignore
    const mp3encoder = new Mp3Encoder(channels, sampleRate, kbps);

    const mp3Data: Int8Array[] = [];

    // Get samples
    const leftData = buffer.getChannelData(0);
    const leftPCM = floatTo16BitPCM(leftData);

    let rightPCM: Int16Array | undefined = undefined;
    if (channels > 1) {
      const rightData = buffer.getChannelData(1);
      rightPCM = floatTo16BitPCM(rightData);
    }

    // Encode in chunks (lamejs recommendation)
    const sampleBlockSize = 1152;
    const totalBlocks = Math.ceil(leftPCM.length / sampleBlockSize);

    for (let i = 0; i < leftPCM.length; i += sampleBlockSize) {
      const leftChunk = leftPCM.subarray(i, i + sampleBlockSize);
      const rightChunk = rightPCM ? rightPCM.subarray(i, i + sampleBlockSize) : undefined;

      const mp3buf = mp3encoder.encodeBuffer(leftChunk, rightChunk);
      if (mp3buf.length > 0) {
        mp3Data.push(mp3buf);
      }

      // Yield manually to UI thread every 50 blocks (~1.2 seconds of audio)
      const currentBlock = Math.floor(i / sampleBlockSize);
      if (currentBlock % 100 === 0) {
        await new Promise(resolve => setTimeout(resolve, 0));
        if (onProgress) {
          onProgress((currentBlock / totalBlocks) * 100);
        }
      }
    }

    // Flush
    const mp3buf = mp3encoder.flush();
    if (mp3buf.length > 0) {
      mp3Data.push(mp3buf);
    }

    return new Blob(mp3Data, { type: 'audio/mp3' });
  } catch (e) {
    console.error("MP3 Encoding Failed:", e);
    console.warn("Falling back to WAV encoding...");
    return encodeWAV(buffer);
  }
}


/**
 * Encodes an AudioBuffer to a WAV file Blob.
 */
export function encodeWAV(buffer: AudioBuffer): Blob {
  const numChannels = buffer.numberOfChannels;
  const sampleRate = buffer.sampleRate;
  const format = 1; // PCM
  const bitDepth = 16;

  let result: Float32Array;
  if (numChannels === 2) {
    const left = buffer.getChannelData(0);
    const right = buffer.getChannelData(1);
    result = new Float32Array(left.length + right.length);
    for (let i = 0; i < left.length; i++) {
      result[i * 2] = left[i];
      result[i * 2 + 1] = right[i];
    }
  } else {
    result = buffer.getChannelData(0);
  }

  const bytesPerSample = bitDepth / 8;
  const blockAlign = numChannels * bytesPerSample;
  const byteRate = sampleRate * blockAlign;
  const dataSize = result.length * bytesPerSample;
  const headerSize = 44;
  const totalSize = headerSize + dataSize;

  const arrayBuffer = new ArrayBuffer(totalSize);
  const view = new DataView(arrayBuffer);

  const writeString = (offset: number, string: string) => {
    for (let i = 0; i < string.length; i++) {
      view.setUint8(offset + i, string.charCodeAt(i));
    }
  };

  // RIFF chunk
  writeString(0, 'RIFF');
  view.setUint32(4, 36 + dataSize, true);
  writeString(8, 'WAVE');

  // fmt subchunk
  writeString(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, format, true);
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitDepth, true);

  // data subchunk
  writeString(36, 'data');
  view.setUint32(40, dataSize, true);

  // Write PCM samples
  const offset = 44;
  for (let i = 0; i < result.length; i++) {
    const s = Math.max(-1, Math.min(1, result[i]));
    const val = s < 0 ? s * 0x8000 : s * 0x7FFF;
    view.setInt16(offset + i * 2, val, true);
  }

  return new Blob([arrayBuffer], { type: 'audio/wav' });
}
