import { useState, useRef, useEffect } from "react";
import { Mic, MicOff, RotateCcw, MapPin, AlertCircle, Bird, Upload } from "lucide-react";
import { useRecorder } from "./useRecorder";
import "./App.css";

const BACKEND_URL = "https://dillonld-birdrecord.hf.space";

function WaveVisualizer({ analyserNode, isActive }) {
  const canvasRef = useRef(null);
  const rafRef    = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const W = canvas.width, H = canvas.height;

    if (!isActive || !analyserNode) {
      ctx.clearRect(0, 0, W, H);
      ctx.strokeStyle = "rgba(134,239,172,0.25)";
      ctx.lineWidth   = 1.5;
      ctx.beginPath();
      ctx.moveTo(0, H / 2);
      ctx.lineTo(W, H / 2);
      ctx.stroke();
      return;
    }

    const bufLen  = analyserNode.frequencyBinCount;
    const dataArr = new Uint8Array(bufLen);

    function draw() {
      rafRef.current = requestAnimationFrame(draw);
      analyserNode.getByteTimeDomainData(dataArr);
      ctx.clearRect(0, 0, W, H);
      ctx.shadowBlur  = 8;
      ctx.shadowColor = "#4ade80";
      ctx.strokeStyle = "#4ade80";
      ctx.lineWidth   = 2;
      ctx.beginPath();
      const sliceW = W / bufLen;
      let x = 0;
      for (let i = 0; i < bufLen; i++) {
        const y = ((dataArr[i] / 128.0) * H) / 2;
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        x += sliceW;
      }
      ctx.lineTo(W, H / 2);
      ctx.stroke();
      ctx.shadowBlur = 0;
    }

    draw();
    return () => cancelAnimationFrame(rafRef.current);
  }, [analyserNode, isActive]);

  return <canvas ref={canvasRef} width={480} height={80} className="wave-canvas" />;
}

function ConfidenceBar({ score }) {
  const pct   = Math.round(score * 100);
  const color = pct >= 75 ? "#4ade80" : pct >= 50 ? "#facc15" : "#f87171";
  return (
    <div>
      <div className="conf-row">
        <span className="conf-label">CONFIDENCE</span>
        <span className="conf-label" style={{ color }}>{pct}%</span>
      </div>
      <div className="conf-track">
        <div className="conf-fill" style={{ width: `${pct}%`, background: color, boxShadow: `0 0 8px ${color}` }} />
      </div>
    </div>
  );
}

function ResultCard({ result }) {
  return (
    <div className="card fadein">
      <div className="card-header">
        <div className="card-icon"><Bird size={22} color="#4ade80" /></div>
        <div>
          <h2 className="card-name">{result.common_name}</h2>
          <p className="card-sci">{result.scientific_name}</p>
        </div>
      </div>
      <ConfidenceBar score={result.confidence} />
      <div>
        <p className="regions-label">Common Regions</p>
        <div className="regions-list">
          {result.regions.map((r) => (
            <span key={r} className="region-tag"><MapPin size={10} />{r}</span>
          ))}
        </div>
      </div>
      {result.start_time !== undefined && (
        <p className="det-time">Detected at {result.start_time.toFixed(1)}s - {result.end_time.toFixed(1)}s</p>
      )}
    </div>
  );
}

function TimerRing({ progress, elapsed }) {
  const r    = 54;
  const circ = 2 * Math.PI * r;
  const dash = circ * (1 - progress);
  const secs = Math.ceil((10000 - elapsed) / 1000);
  return (
    <div className="timer-ring">
      <svg width={140} height={140} className="timer-svg">
        <circle cx={70} cy={70} r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={4} />
        <circle cx={70} cy={70} r={r} fill="none" stroke="#4ade80" strokeWidth={4}
          strokeDasharray={circ} strokeDashoffset={dash} strokeLinecap="round"
          style={{ transition: "stroke-dashoffset 0.05s linear", filter: "drop-shadow(0 0 6px #4ade80)" }}
        />
      </svg>
      <span className="timer-number">{secs}</span>
    </div>
  );
}

function Spinner({ label }) {
  return (
    <div className="spinner-wrap">
      <svg className="spin" width={36} height={36} viewBox="0 0 36 36">
        <circle cx={18} cy={18} r={15} fill="none" stroke="rgba(74,222,128,0.2)" strokeWidth={3} />
        <path d="M18 3 a15 15 0 0 1 15 15" fill="none" stroke="#4ade80" strokeWidth={3} strokeLinecap="round" />
      </svg>
      <p className="spinner-text">{label || "Analyzing audio..."}</p>
    </div>
  );
}

export default function App() {
  const { phase, audioBlob, elapsed, progress, analyserNode, errorMsg, start, stop, reset } = useRecorder();
  const [results,      setResults]      = useState([]);
  const [apiError,     setApiError]     = useState("");
  const [loading,      setLoading]      = useState(false);
  const [backendReady, setBackendReady] = useState(false);
  const [uploadName,   setUploadName]   = useState("");
  const fileInputRef = useRef(null);

  // Wake up backend on page load
  useEffect(() => {
    fetch(`${BACKEND_URL}/health`)
      .then(r => { if (r.ok) setBackendReady(true); })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (phase === "done" && audioBlob) analyze(audioBlob, "recording.webm");
  }, [phase, audioBlob]);

  async function analyze(blob, filename) {
    setLoading(true);
    setApiError("");
    setResults([]);
    const form = new FormData();
    form.append("audio", blob, filename || "recording.webm");
    try {
      const res  = await fetch(`${BACKEND_URL}/analyze`, { method: "POST", body: form });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Server error ${res.status}`);
      }
      const data = await res.json();
      setResults(data.detections || []);
      if ((data.detections || []).length === 0)
        setApiError("No bird species detected. Try a clearer recording or a file with more bird sounds.");
    } catch (e) {
      setApiError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function handleFileUpload(e) {
    const file = e.target.files[0];
    if (!file) return;
    setUploadName(file.name);
    setApiError("");
    setResults([]);
    reset();
    analyze(file, file.name);
    // Reset input so same file can be re-uploaded
    e.target.value = "";
  }

  const isRecording  = phase === "recording";
  const isProcessing = phase === "processing" || loading;
  const showResults  = !isRecording && !isProcessing && results.length > 0;
  const showError    = (phase === "error" && errorMsg) || apiError;

  return (
    <div className="page">
      <div className="container">

        <div className="header">
          <div className="header-rule">
            <div className="header-rule-line left" />
            <span className="header-label">Bioacoustic AI</span>
            <div className="header-rule-line right" />
          </div>
          <h1 className="header-title">BirdNET</h1>
          <p className="header-sub">Record ambient audio - Identify species - Discover habitats</p>
          <div className="backend-status">
            <span className={`status-dot ${backendReady ? "dot-ready" : "dot-warming"}`} />
            <span className="status-dot-label">
              {backendReady ? "Backend ready" : "Warming up backend..."}
            </span>
          </div>
        </div>

        <div className="panel">
          <WaveVisualizer analyserNode={analyserNode} isActive={isRecording} />

          <div className="status">
            {isRecording  && <TimerRing progress={progress} elapsed={elapsed} />}
            {isProcessing && <Spinner label={uploadName ? `Analyzing ${uploadName}...` : "Analyzing audio..."} />}
            {!isRecording && !isProcessing && (
              <p className="status-text">
                {phase === "idle"
                  ? "Record live audio or upload an audio file"
                  : "Analysis complete"}
              </p>
            )}
          </div>

          {/* Buttons */}
          <div className="btn-row">
            {!isRecording && !isProcessing && (
              <>
                <button
                  className={phase === "idle" ? "btn-start" : "btn-reset"}
                  onClick={phase === "idle" ? start : () => { reset(); setUploadName(""); setResults([]); setApiError(""); }}
                >
                  {phase === "idle"
                    ? <><Mic size={15} /> Record</>
                    : <><RotateCcw size={14} /> Reset</>}
                </button>

                <button className="btn-upload" onClick={() => fileInputRef.current.click()}>
                  <Upload size={15} /> Upload File
                </button>

                <input
                  ref={fileInputRef}
                  type="file"
                  accept="audio/*,.mp3,.wav,.ogg,.flac,.m4a"
                  style={{ display: "none" }}
                  onChange={handleFileUpload}
                />
              </>
            )}

            {isRecording && (
              <button className="btn-stop pulse-ring" onClick={stop}>
                <MicOff size={15} /> Stop
              </button>
            )}
          </div>

          {uploadName && !isProcessing && (
            <p className="upload-name">File: {uploadName}</p>
          )}
        </div>

        {showError && (
          <div className="error-box fadein">
            <AlertCircle size={18} color="#f87171" style={{ flexShrink: 0, marginTop: 1 }} />
            <p className="error-text">{errorMsg || apiError}</p>
          </div>
        )}

        {showResults && (
          <div className="results fadein">
            <p className="results-label">
              {results.length} Detection{results.length !== 1 ? "s" : ""} Found
            </p>
            {results.map((r, i) => <ResultCard key={i} result={r} />)}
          </div>
        )}

        <p className="footer">Powered by BirdNET - Cornell Lab of Ornithology</p>
      </div>
    </div>
  );
}