
import fs from "fs";
import path from "path";

async function listModelsDetailed() {
    let API_KEY = process.env.GEMINI_API_KEY || process.env.API_KEY;

    if (!API_KEY) {
        const envPath = path.resolve(".env.local");
        if (fs.existsSync(envPath)) {
            const lines = fs.readFileSync(envPath, 'utf8').split('\n');
            for (const line of lines) {
                if (line.trim().startsWith("GEMINI_API_KEY=")) {
                    API_KEY = line.trim().split("=")[1].replace(/["']/g, "");
                    break;
                }
            }
        }
    }

    if (!API_KEY) {
        console.error("No API KEY found");
        return;
    }

    try {
        const url = `https://generativelanguage.googleapis.com/v1beta/models?key=${API_KEY}`;
        const response = await fetch(url);
        const data = await response.json();

        if (data.models) {
            const ttsModels = data.models.filter(m =>
                m.name.includes("tts") ||
                m.supportedSupportedResponseModalities?.includes("audio") ||
                m.description?.toLowerCase().includes("speech")
            );
            console.log("Potential TTS/Audio Models:");
            console.log(JSON.stringify(ttsModels, null, 2));

            console.log("\nAll Models (Names only):");
            data.models.forEach(m => console.log(`- ${m.name}`));
        } else {
            console.log("No models found in response:", data);
        }
    } catch (e) {
        console.error("Error listing models:", e);
    }
}

listModelsDetailed();
