
import { spawn } from 'child_process';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// LOGIC TO BE ADDED TO index.js
const isWindows = process.platform === 'win32';
const venvPythonStr = isWindows ? 'Scripts/python.exe' : 'bin/python';
const venvPath = path.join(__dirname, '../.venv', venvPythonStr);
const pythonCmd = fs.existsSync(venvPath) ? venvPath : 'python';

console.log(`[Test] Detected Python Command: ${pythonCmd}`);

async function runCommand(command, args) {
    return new Promise((resolve, reject) => {
        console.log(`[Test] Spawning: ${command} ${args.join(' ')}`);
        const proc = spawn(command, args);
        let stdout = '';
        let stderr = '';
        proc.stdout.on('data', d => stdout += d.toString());
        proc.stderr.on('data', d => stderr += d.toString());
        proc.on('close', code => {
            if (code === 0) resolve(stdout.trim());
            else reject(new Error(stderr || stdout));
        });
    });
}

async function test() {
    const text = "This is a test audio generation from the verification script.";
    const speaker = "Ben";
    const outputFile = path.join(__dirname, '../output/test_fix_audio.pcm');

    // Ensure output dir
    if (!fs.existsSync(path.dirname(outputFile))) fs.mkdirSync(path.dirname(outputFile));

    try {
        await runCommand(pythonCmd, [
            path.join(__dirname, 'poddub_tts.py'),
            '--text', text,
            '--speaker', speaker,
            '--output', outputFile
        ]);

        if (fs.existsSync(outputFile) && fs.statSync(outputFile).size > 0) {
            console.log("SUCCESS: Audio file created successfully.");
        } else {
            console.error("FAILURE: File not created or empty.");
        }
    } catch (e) {
        console.error("FAILURE: Script execution error:", e.message);
    }
}

test();
