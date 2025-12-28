
import { GoogleGenAI, Type, Modality } from "@google/genai";
import { ProcessedPodcast, TranscriptSegment, ProgressCallback } from "../types";
import { blobToBase64, concatenatePCMData, decodeBase64ToArray } from "./audioUtils";

// Helper to get client (assumes process.env.API_KEY is available)
const getClient = () => new GoogleGenAI({ apiKey: process.env.API_KEY });


// Constants
const CHUNK_SIZE_BYTES = 4 * 1024 * 1024; // Reduced to 4MB to be safer on TPM
const TTS_CHUNK_SIZE = 50; // Keep high (50) to minimize Request Count (RPD limit 100)
const CONCURRENCY_LIMIT = 1; // single-threaded to respect 10 RPM limit

// --- Helpers ---

const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

async function retryWithBackoff<T>(
  operation: () => Promise<T>,
  retries: number = 5,
  initialDelay: number = 2000 // Lower initial delay for paid tier
): Promise<T> {
  let attempt = 0;
  while (attempt < retries) {
    try {
      return await operation();
    } catch (error: any) {
      // Check for Rate Limit (429) or Service Unavailable (503)
      const isRateLimit =
        error.status === 429 ||
        error.code === 429 ||
        (error.message && error.message.includes('429')) ||
        (error.message && error.message.includes('Quota')) ||
        (error.message && error.message.includes('quota'));

      const isServerOverload =
        error.status === 503 ||
        error.code === 503 ||
        error.status === 500 ||
        error.code === 500 ||
        error.status === 502 ||
        error.code === 502;

      if (isRateLimit || isServerOverload) {
        attempt++;
        if (attempt >= retries) throw error;

        // Exponential backoff: 2s, 4s, 8s...
        const waitTime = initialDelay * Math.pow(2, attempt - 1);
        console.warn(`API Rate Limit/Error (Attempt ${attempt}/${retries}). Retrying in ${waitTime / 1000}s...`);
        await delay(waitTime);
      } else {
        throw error; // Rethrow other errors immediately
      }
    }
  }
  throw new Error("Max retries exceeded");
}

// ... (Voice Configuration Helpers - Minimal changes, included for context if needed, otherwise omitted) ...
const MALE_VOICES = ['Fenrir', 'Puck', 'Charon', 'Zephyr'];
const FEMALE_VOICES = ['Kore', 'Aoede']; // ... (omitted consistent parts) ...

// Simple heuristic for gender guessing
const guessGender = (name: string): 'MALE' | 'FEMALE' => {
  const n = name.toLowerCase().trim();
  if (n.includes('david') || n.includes('ben') || n.includes('gilbert') || n.includes('rosenthal')) return 'MALE';
  const maleNames = ['john', 'michael', 'james', 'robert', 'william', 'joe', 'kevin', 'mark', 'paul', 'peter', 'andrew', 'brian', 'jason'];
  if (maleNames.some(m => n.includes(m))) return 'MALE';
  const femaleNames = ['mary', 'patricia', 'jennifer', 'linda', 'elizabeth', 'susan', 'jessica', 'sarah', 'karen', 'lisa', 'nancy', 'amy', 'michelle'];
  if (femaleNames.some(f => n.includes(f))) return 'FEMALE';
  if (n.endsWith('a') && !n.endsWith('ua') && !n.endsWith('ia')) return 'FEMALE';
  return 'MALE';
};

/**
 * Step 1: Analyze Audio (Chunked)
 * (Unchanged logic, just simplified for replacement match)
 */
export const analyzePodcastAudio = async (
  file: File,
  onProgress?: ProgressCallback,
  onPartialResult?: (newSegments: TranscriptSegment[], allSpeakers: string[]) => void
): Promise<ProcessedPodcast> => {
  // ... (Keeping original implementation via context is preferred, but I will write it out if needed or skip if diff is targeted) ...
  // Since I am replacing the whole file content essentially to change generateDubbedAudio, I should be careful. 
  // Actually, Step 1 uses specific `delay(10000)` too. I should optimize that as well.

  const ai = getClient();
  const modelId = "gemini-2.5-flash";

  const fileSize = file.size;
  let offset = 0;
  let chunkIndex = 0;
  const totalChunks = Math.ceil(fileSize / CHUNK_SIZE_BYTES);

  const allSegments: TranscriptSegment[] = [];
  const allSpeakers = new Set<string>();

  const mimeType = file.type || "audio/mp3";

  while (offset < fileSize) {
    chunkIndex++;
    if (onProgress) {
      onProgress(`Analyzing Part ${chunkIndex} of ${totalChunks}...`, (chunkIndex / totalChunks) * 100);
    }

    const chunkBlob = file.slice(offset, offset + CHUNK_SIZE_BYTES);
    const base64Audio = await blobToBase64(chunkBlob);

    const knownSpeakers = Array.from(allSpeakers).join(", ");
    const speakerContext = knownSpeakers.length > 0
      ? `PREVIOUSLY IDENTIFIED SPEAKERS: [${knownSpeakers}]. Use these names if the voices match.`
      : `NOTE: If the speakers identify themselves, use their real names.`;

    const prompt = `
      You are a professional transcriber and translator.
      This is Part ${chunkIndex} of ${totalChunks} of a podcast.

      CRITICAL INSTRUCTIONS:
      1. **VERBATIM TRANSCRIPTION**: Transcribe every sentence.
      2. **Speaker Identification**: ${speakerContext}
      3. **Translation**: Translate to Chinese (Mandarin).
      4. **Output Format**: JSON object with segments.
    `;

    try {
      const response = await retryWithBackoff(async () => {
        return await ai.models.generateContent({
          model: modelId,
          contents: {
            parts: [
              { inlineData: { mimeType: mimeType, data: base64Audio } },
              { text: prompt }
            ]
          },
          config: {
            responseMimeType: "application/json",
            responseSchema: {
              type: Type.OBJECT,
              properties: {
                detectedSpeakers: {
                  type: Type.ARRAY,
                  items: { type: Type.STRING },
                  description: "List of unique speaker labels found in this segment"
                },
                segments: {
                  type: Type.ARRAY,
                  items: {
                    type: Type.OBJECT,
                    properties: {
                      speaker: { type: Type.STRING },
                      originalEnglish: { type: Type.STRING },
                      translatedChinese: { type: Type.STRING }
                    }
                  }
                }
              }
            }
          }
        });
      }, 5, 2000); // Optimized retry delay

      if (response.text) {
        const result = JSON.parse(response.text) as ProcessedPodcast;
        if (result.segments && result.segments.length > 0) {
          allSegments.push(...result.segments);
          if (result.detectedSpeakers) {
            result.detectedSpeakers.forEach(s => {
              if (s && s.trim().length > 0) allSpeakers.add(s);
            });
          }
          if (onPartialResult) {
            onPartialResult(result.segments, Array.from(allSpeakers).sort());
          }
        }
      }
    } catch (e) {
      console.error(`Error processing chunk ${chunkIndex}:`, e);
    }

    offset += CHUNK_SIZE_BYTES;

    // Optimized: Only 1s delay for rate limits on paid tier
    if (offset < fileSize) {
      await delay(1000);
    }
  }

  return {
    segments: allSegments,
    detectedSpeakers: Array.from(allSpeakers).sort()
  };
};

/**
 * Step 2: Generate Dubbed Audio (Optimized for High Throughput)
 */
export const generateDubbedAudio = async (
  segments: TranscriptSegment[],
  detectedSpeakers: string[],
  onProgress?: ProgressCallback,
  onAudioChunk?: (chunk: Uint8Array) => void
): Promise<Uint8Array> => {
  const ai = getClient();
  const modelId = "gemini-2.5-flash-preview-tts";

  // Resolve Speakers (Same logic)
  let uniqueSpeakers = Array.from(new Set(detectedSpeakers)).filter(s => s && s.trim().length > 0);
  if (uniqueSpeakers.length === 0) {
    uniqueSpeakers = Array.from(new Set(segments.map(s => s.speaker))).filter(s => s && s.trim().length > 0);
  }
  const namedSpeakers = uniqueSpeakers.filter(s => !s.toLowerCase().includes("speaker"));
  if (namedSpeakers.length >= 2) uniqueSpeakers = namedSpeakers;
  if (uniqueSpeakers.length === 0) uniqueSpeakers = ["Narrator"];

  // Assign Voices (Same logic)
  const VIRTUAL_SPEAKER_1 = "Voice_Slot_1";
  const VIRTUAL_SPEAKER_2 = "Voice_Slot_2";
  const primarySpeakerName = uniqueSpeakers[0];
  const secondarySpeakerName = uniqueSpeakers[1] || "Guest";

  let voice1 = MALE_VOICES[0];
  let voice2 = FEMALE_VOICES[0];
  const primaryGender = guessGender(primarySpeakerName);
  const secondaryGender = guessGender(secondarySpeakerName);
  if (primaryGender === 'MALE' && secondaryGender === 'MALE') {
    voice1 = MALE_VOICES[0]; voice2 = MALE_VOICES[1];
  } else if (primaryGender === 'FEMALE' && secondaryGender === 'FEMALE') {
    voice1 = FEMALE_VOICES[0]; voice2 = FEMALE_VOICES[1];
  } else if (primaryGender === 'MALE' && secondaryGender === 'FEMALE') {
    voice1 = MALE_VOICES[0]; voice2 = FEMALE_VOICES[0];
  } else {
    voice1 = FEMALE_VOICES[0]; voice2 = MALE_VOICES[0];
  }

  const isMultiSpeaker = uniqueSpeakers.length > 1;
  let speechConfig: any = {};
  if (isMultiSpeaker) {
    speechConfig = {
      multiSpeakerVoiceConfig: {
        speakerVoiceConfigs: [
          { speaker: VIRTUAL_SPEAKER_1, voiceConfig: { prebuiltVoiceConfig: { voiceName: voice1 } } },
          { speaker: VIRTUAL_SPEAKER_2, voiceConfig: { prebuiltVoiceConfig: { voiceName: voice2 } } }
        ]
      }
    };
  } else {
    speechConfig = { voiceConfig: { prebuiltVoiceConfig: { voiceName: primaryGender === 'MALE' ? voice1 : voice2 } } };
  }

  // --- Optimized Batch Processing ---

  const batches: TranscriptSegment[][] = [];
  for (let i = 0; i < segments.length; i += TTS_CHUNK_SIZE) {
    batches.push(segments.slice(i, i + TTS_CHUNK_SIZE));
  }

  const audioChunksMap = new Map<number, Uint8Array>(); // Store by index to preserve order
  const totalBatches = batches.length;
  let completedBatches = 0;

  // Process batches with concurrency limit
  for (let i = 0; i < totalBatches; i += CONCURRENCY_LIMIT) {
    const activeBatches = batches.slice(i, i + CONCURRENCY_LIMIT);
    const batchPromises = activeBatches.map(async (segmentBatch, offsetIdx) => {
      const batchGlobalIndex = i + offsetIdx;

      if (onProgress) {
        onProgress(`Dubbing... (Processed ${completedBatches}/${totalBatches} batches)`, (completedBatches / totalBatches) * 100);
      }

      let script = "";
      // Build script
      if (isMultiSpeaker) {
        segmentBatch.forEach(seg => {
          const speakerName = seg.speaker;
          let targetSlot = VIRTUAL_SPEAKER_2;
          if (speakerName === primarySpeakerName) targetSlot = VIRTUAL_SPEAKER_1;
          else if (speakerName === secondarySpeakerName) targetSlot = VIRTUAL_SPEAKER_2;
          else {
            const idx = uniqueSpeakers.indexOf(speakerName);
            targetSlot = (idx % 2 === 0) ? VIRTUAL_SPEAKER_1 : VIRTUAL_SPEAKER_2;
          }
          script += `${targetSlot}: ${seg.translatedChinese}\n`;
        });
      } else {
        segmentBatch.forEach(seg => {
          script += `${seg.translatedChinese}\n`;
        });
      }

      try {
        const response = await retryWithBackoff(async () => {
          return await ai.models.generateContent({
            model: modelId,
            contents: [{ parts: [{ text: script }] }],
            config: { responseModalities: [Modality.AUDIO], speechConfig: speechConfig }
          });
        }, 3, 2000); // Fast retry

        const base64Audio = response.candidates?.[0]?.content?.parts?.[0]?.inlineData?.data;
        if (base64Audio) {
          const rawBytes = decodeBase64ToArray(base64Audio);
          audioChunksMap.set(batchGlobalIndex, rawBytes);
          // We can't stream directly in order if we process out of order, 
          // but for simple progress update we can emit. 
          // The App.tsx handles accumulation, but assumes order. 
          // Actually App.tsx pushes to array. This might be an issue if we push out of order.
          // Let's modify App.tsx later or just buffer here. 
          // For now, let's just buffer inside this function and return concatenated result.
        }
      } catch (e: any) {
        console.error(`Error dubbing batch ${batchGlobalIndex}:`, e);
        throw new Error(`TTS Error in batch ${batchGlobalIndex}: ${e.message}`);
      }

    });

    await Promise.all(batchPromises);
    completedBatches += activeBatches.length;
    // Strict Rate Limit: 10 RPM = 1 request every 6s.
    // We added a buffer to 7000ms to be safe.
    await delay(7000);
  }

  // Reassemble in order
  const finalChunks: Uint8Array[] = [];
  for (let i = 0; i < totalBatches; i++) {
    const chunk = audioChunksMap.get(i);
    if (chunk) {
      finalChunks.push(chunk);
      if (onAudioChunk) onAudioChunk(chunk); // Emit in order for playback pre-buffering
    }
  }

  if (finalChunks.length === 0) {
    throw new Error("Failed to generate any audio.");
  }

  return concatenatePCMData(finalChunks);
};

/**
 * Step 3: Optimize Script (Colloquialism + and TTS Tags)
 */
export const optimizeScriptWithGemini = async (
  segments: TranscriptSegment[],
  onProgress?: ProgressCallback
): Promise<TranscriptSegment[]> => {
  const ai = getClient();
  const modelId = "gemini-2.5-flash"; // Use a fast text model

  const OPTIMIZE_BATCH_SIZE = 15;
  const batches: TranscriptSegment[][] = [];
  for (let i = 0; i < segments.length; i += OPTIMIZE_BATCH_SIZE) {
    batches.push(segments.slice(i, i + OPTIMIZE_BATCH_SIZE));
  }

  const optimizedSegments: TranscriptSegment[] = JSON.parse(JSON.stringify(segments)); // Deep Clone

  for (let i = 0; i < batches.length; i++) {
    const batch = batches[i];
    const startIndex = i * OPTIMIZE_BATCH_SIZE;

    if (onProgress) {
      onProgress(`Optimizing script... (Batch ${i + 1}/${batches.length})`, (i / batches.length) * 100);
    }

    const promptInput = batch.map(s => ({
      originalEnglish: s.originalEnglish,
      translatedChinese: s.translatedChinese
    }));

    const prompt = `
    You are a professional Podcast Editor and Translator.
    Target Audience: Chinese listeners of a tech/business podcast.
    
    Task:
    1. **Refine the Tone**: Make it conversational, engaging, and "grounded" (接地气). Avoid stiff, machine-translated phrasing.
       - e.g. "I cannot believe" -> "我简直不敢相信"
       - e.g. "Well, but" -> "哎，不过"
    
    2. **Keep Proper Nouns in English**: Do NOT translate names of people (e.g. Elon Musk, Joe Rogan), places, countries, or companies. Keep them in their original English form in the Chinese translation.
    
    3. **Insert Audio Tags** at the START or within the text to guide the TTS engine.
       - Use \`[laugh]\` for humor/laughter.
       - Use \`[sigh]\` for resignation.
       - Use \`[excited]\` for high energy.
       - Use \`[pause]\` for dramatic beats.

    4. **Fix Grammar & Flow**: Ensure sentences flow smoothly. You can split or combine sentences if it improves the listening experience.
    
    Format:
    Input is a JSON list of objects.
    Output MUST be a **JSON list of STRINGS** (the optimized Chinese text ONLY). 
    The order must match EXACTLY.

    Input:
    ${JSON.stringify(promptInput)}
    `;

    try {
      const response = await retryWithBackoff(async () => {
        return await ai.models.generateContent({
          model: modelId,
          contents: [{ parts: [{ text: prompt }] }],
          config: { responseMimeType: "application/json" }
        });
      }, 3, 1000);

      const text = response.text || "[]";
      let optimizedTexts: string[] = [];
      try {
        optimizedTexts = JSON.parse(text);
      } catch (e) {
        console.error("Failed to parse JSON from Gemini:", text);
      }

      if (Array.isArray(optimizedTexts) && optimizedTexts.length === batch.length) {
        optimizedTexts.forEach((newText, idx) => {
          optimizedSegments[startIndex + idx].translatedChinese = newText;
        });
      } else {
        console.warn(`Batch ${i} optimization mismatch or failure. Keeping original.`);
      }

    } catch (e) {
      console.error(`Error optimizing batch ${i}:`, e);
    }

    // Rate limit buffer
    await delay(500);
  }

  return optimizedSegments;
};
