
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Path to the project file provided by the user
const PROJECT_FILE = "d:\\MingggSync\\Playground\\Podcast_Tools\\Google_AI_Podcast_Parts\\part_000_000_project (1).json";

async function runTest() {
    console.log(`[Test] Reading project file: ${PROJECT_FILE}`);

    if (!fs.existsSync(PROJECT_FILE)) {
        console.error(`[Test] Error: Project file not found at ${PROJECT_FILE}`);
        process.exit(1);
    }

    const projectData = JSON.parse(fs.readFileSync(PROJECT_FILE, 'utf-8'));
    const segments = projectData.segments;
    console.log(`[Test] Loaded ${segments.length} segments.`);

    // Test a subset of segments to be quick (e.g., first 5)
    // The user said "Import ... test", implying we should test if it works.
    // Testing the first few is usually sufficient to catch "ModuleNotFound" or configuration errors.
    const segmentsToTest = segments.slice(0, 5);
    let successCount = 0;
    let failCount = 0;

    console.log(`[Test] Testing first ${segmentsToTest.length} segments...`);

    for (let i = 0; i < segmentsToTest.length; i++) {
        const seg = segmentsToTest[i];
        console.log(`\n[Test] Segment ${i + 1}: [${seg.speaker}] ${seg.translatedChinese.substring(0, 30)}...`);

        try {
            const response = await fetch('http://localhost:3001/api/tts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: seg.translatedChinese,
                    speaker: seg.speaker
                })
            });

            if (!response.ok) {
                const errText = await response.text();
                fs.writeFileSync(path.join(__dirname, 'last_error.txt'), errText);
                throw new Error(`HTTP ${response.status}: ${errText.substring(0, 100)}... (saved to last_error.txt)`);
            }

            const blob = await response.blob();
            const arrayBuffer = await blob.arrayBuffer();
            const buffer = Buffer.from(arrayBuffer);

            if (buffer.length > 0) {
                console.log(`[Test] SUCCESS: Received ${buffer.length} bytes of audio.`);
                successCount++;
            } else {
                console.error(`[Test] FAILURE: Received empty audio.`);
                failCount++;
            }

        } catch (e) {
            console.error(`[Test] FAILURE: ${e.message}`);
            failCount++;
        }
    }

    console.log(`\n[Test] Summary: ${successCount} Passed, ${failCount} Failed.`);
    if (failCount === 0) {
        console.log("[Test] ALL TESTS PASSED. The system is ready.");
    } else {
        console.log("[Test] SOME TESTS FAILED. Debugging required.");
        process.exit(1);
    }
}

runTest();
