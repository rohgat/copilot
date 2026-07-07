from __future__ import annotations
import json
import os
from pathlib import Path
from typing import List, Dict, Optional
from .models import TranscriptChunk
from .config import config


class ContextStore:
    """ChromaDB-backed store for transcripts, files, and preference signals."""

    MEETINGS_COLLECTION = "meetings"
    FILES_COLLECTION = "files"
    PREFS_COLLECTION = "preferences"

    def __init__(self):
        self._client = None
        self._meetings = None
        self._files = None
        self._prefs = None
        self._preference_profile: Dict[str, float] = {}
        self._ensure_dirs()

    def _ensure_dirs(self):
        Path(config.CHROMA_PATH).mkdir(parents=True, exist_ok=True)
        Path(config.FILES_DIR).mkdir(parents=True, exist_ok=True)
        Path(config.PREFS_PATH).parent.mkdir(parents=True, exist_ok=True)

    def _load(self):
        if self._client:
            return
        import chromadb
        self._client = chromadb.PersistentClient(path=config.CHROMA_PATH)
        self._meetings = self._client.get_or_create_collection(
            self.MEETINGS_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        self._files = self._client.get_or_create_collection(
            self.FILES_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        self._prefs = self._client.get_or_create_collection(
            self.PREFS_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        self._load_preferences()

    def _load_preferences(self):
        prefs_path = Path(config.PREFS_PATH)
        if prefs_path.exists():
            with open(prefs_path) as f:
                self._preference_profile = json.load(f)

    def _save_preferences(self):
        with open(config.PREFS_PATH, "w") as f:
            json.dump(self._preference_profile, f, indent=2)

    def add_transcript_chunk(self, chunk: TranscriptChunk):
        self._load()
        doc_id = f"{chunk.meeting_id}_{chunk.timestamp}"
        self._meetings.add(
            documents=[chunk.text],
            ids=[doc_id],
            metadatas=[{
                "meeting_id": chunk.meeting_id,
                "speaker": chunk.speaker,
                "timestamp": chunk.timestamp,
            }],
        )

    def add_meeting_summary(self, meeting_id: str, summary: str, title: str, date: str):
        self._load()
        self._meetings.add(
            documents=[summary],
            ids=[f"summary_{meeting_id}"],
            metadatas=[{
                "meeting_id": meeting_id,
                "type": "summary",
                "title": title,
                "date": date,
            }],
        )

    def add_file(self, file_path: str, meeting_id: str, filename: str):
        """Ingest a document file and embed its text content."""
        self._load()
        text = self._extract_text(file_path)
        if not text:
            return
        chunks = self._chunk_text(text, chunk_size=500)
        ids = [f"file_{meeting_id}_{filename}_{i}" for i in range(len(chunks))]
        metas = [
            {
                "meeting_id": meeting_id,
                "filename": filename,
                "chunk_index": i,
                "type": "file",
            }
            for i in range(len(chunks))
        ]
        self._files.add(documents=chunks, ids=ids, metadatas=metas)

    def _extract_text(self, file_path: str) -> str:
        path = Path(file_path)
        suffix = path.suffix.lower()
        try:
            if suffix == ".txt":
                return path.read_text(errors="ignore")
            elif suffix == ".pdf":
                import pdfplumber
                with pdfplumber.open(file_path) as pdf:
                    return "\n".join(p.extract_text() or "" for p in pdf.pages)
            elif suffix in (".docx",):
                from docx import Document
                doc = Document(file_path)
                return "\n".join(p.text for p in doc.paragraphs)
            else:
                return path.read_text(errors="ignore")
        except Exception:
            return ""

    def _chunk_text(self, text: str, chunk_size: int = 500) -> List[str]:
        words = text.split()
        chunks, current = [], []
        for word in words:
            current.append(word)
            if len(current) >= chunk_size:
                chunks.append(" ".join(current))
                current = current[-50:]  # 50-word overlap
        if current:
            chunks.append(" ".join(current))
        return chunks

    def search(self, query: str, meeting_id: Optional[str] = None, n_results: int = 5) -> List[str]:
        self._load()
        results = []
        where = {"meeting_id": meeting_id} if meeting_id else None

        try:
            r = self._meetings.query(
                query_texts=[query],
                n_results=min(n_results, self._meetings.count()),
                where=where,
            )
            if r and r["documents"]:
                results.extend(r["documents"][0])
        except Exception:
            pass

        try:
            file_where = {"meeting_id": meeting_id} if meeting_id else None
            r = self._files.query(
                query_texts=[query],
                n_results=min(3, self._files.count()),
                where=file_where,
            )
            if r and r["documents"]:
                results.extend(r["documents"][0])
        except Exception:
            pass

        return results[:n_results]

    def add_preference(self, text: str, weight: float = 1.0):
        """Record a positive preference signal (starred bullet)."""
        self._load()
        pref_id = f"pref_{hash(text) & 0xFFFFFFFF}"
        self._prefs.upsert(
            documents=[text],
            ids=[pref_id],
            metadatas=[{"weight": weight}],
        )
        key = text[:80]
        self._preference_profile[key] = self._preference_profile.get(key, 0) + weight
        self._save_preferences()

    def get_preference_context(self, query: str, n: int = 3) -> List[str]:
        self._load()
        if self._prefs.count() == 0:
            return []
        try:
            r = self._prefs.query(query_texts=[query], n_results=min(n, self._prefs.count()))
            return r["documents"][0] if r and r["documents"] else []
        except Exception:
            return []
