import { useState, useRef, useCallback, useEffect } from "react";

const MAX_DURATION_MS = 10000;

export function useRecorder() {
  const [phase, setPhase] = useState("idle"); // idle | recording | processing | done | error
  const [audioBlob, setAudioBlob] = useState(null);
  const [elapsed, setElapsed] = useState(0);
  const [analyserNode, setAnalyserNode] = useState(null);
  const [errorMsg, setErrorMsg] = useState("");

  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const streamRef = useRef(null);
  const audioCtxRef = useRef(null);
  const timerRef = useRef(null);
  const startTimeRef = useRef(null);

  // Tick elapsed time
  useEffect(() => {
    if (phase === "recording") {
      startTimeRef.current = Date.now();
      timerRef.current = setInterval(() => {
        const diff = Date.now() - startTimeRef.current;
        setElapsed(Math.min(diff, MAX_DURATION_MS));
      }, 50);
    } else {
      clearInterval(timerRef.current);
      if (phase !== "idle") return;
      setElapsed(0);
    }
    return () => clearInterval(timerRef.current);
  }, [phase]);

  const start = useCallback(async () => {
    setErrorMsg("");
    setAudioBlob(null);
    setElapsed(0);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      // Build analyser for visualizer
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      audioCtxRef.current = ctx;
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      setAnalyserNode(analyser);

      // Prefer webm/ogg, fallback to whatever browser supports
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/ogg;codecs=opus")
        ? "audio/ogg;codecs=opus"
        : "";

      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});
      mediaRecorderRef.current = recorder;
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, {
          type: mimeType || "audio/webm",
        });
        setAudioBlob(blob);
        setPhase("done");
        cleanup();
      };

      recorder.start(100); // collect chunks every 100ms
      setPhase("recording");

      // Auto-stop after 10s
      setTimeout(() => {
        if (
          mediaRecorderRef.current &&
          mediaRecorderRef.current.state === "recording"
        ) {
          stop();
        }
      }, MAX_DURATION_MS);
    } catch (err) {
      setErrorMsg(
        err.name === "NotAllowedError"
          ? "Microphone access denied. Please allow mic permissions and try again."
          : `Could not access microphone: ${err.message}`
      );
      setPhase("error");
    }
  }, []);

  const stop = useCallback(() => {
    if (
      mediaRecorderRef.current &&
      mediaRecorderRef.current.state === "recording"
    ) {
      mediaRecorderRef.current.stop();
      setPhase("processing");
    }
  }, []);

  const reset = useCallback(() => {
    cleanup();
    setAudioBlob(null);
    setElapsed(0);
    setErrorMsg("");
    setPhase("idle");
    setAnalyserNode(null);
  }, []);

  function cleanup() {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (audioCtxRef.current) {
      audioCtxRef.current.close().catch(() => {});
      audioCtxRef.current = null;
    }
  }

  const progress = elapsed / MAX_DURATION_MS; // 0 → 1

  return { phase, audioBlob, elapsed, progress, analyserNode, errorMsg, start, stop, reset };
}