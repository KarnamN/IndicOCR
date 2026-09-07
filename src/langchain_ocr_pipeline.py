"""
LangChain + LangGraph OCR Pipeline
Orchestrates OCR processing with state management, engine routing, and fallback logic.
"""
import time
import logging
from typing import TypedDict, Optional, List, Dict, Any
from PIL import Image

import config
from logging_config import get_logger

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════
#  State Definition
# ═══════════════════════════════════════════════════════

class PageOCRState(TypedDict):
    """State for processing a single page through the OCR pipeline."""
    # Input
    page_image: Any           # PIL Image
    page_num: int
    language: str
    
    # Analysis results
    complexity_score: float
    has_table: bool
    has_illustrations: bool
    has_mixed_content: bool
    is_multicolumn: bool
    num_columns: int
    text_region: Any          # (y_start, y_end) or None
    column_gutter_x: Any     # int or None
    image_regions: List       # [(x, y, w, h), ...]
    analysis_time_ms: float
    
    # OCR results
    engine_used: str          # 'tesseract', 'easyocr', 'gemini'
    recommended_engine: str
    extracted_text: str
    ocr_time_ms: float
    ocr_failed: bool
    
    # Post-processing
    post_processed_text: str
    post_process_time_ms: float
    
    # Fallback tracking
    retry_count: int
    fallback_chain: List[str]  # engines tried in order
    
    # Overall timing
    total_time_ms: float
    reasoning: str


# ═══════════════════════════════════════════════════════
#  LangGraph Pipeline
# ═══════════════════════════════════════════════════════

class LangGraphOCRPipeline:
    """
    LangGraph-based OCR pipeline with:
    - Complexity analysis node
    - Engine routing (conditional edges)
    - OCR execution nodes (Tesseract, EasyOCR, Gemini)
    - Post-processing node
    - Automatic fallback on failure
    
    This provides structured state management and clear pipeline visualization
    compared to the legacy direct-call approach.
    """
    
    def __init__(self):
        self._graph = None
        self._compiled = False
        self._analyzer = None
        self._processors = {}  # Cached OCR processors
        
        # Lazy imports to avoid circular dependencies
        self._build_pipeline()
    
    def _build_pipeline(self):
        """Build the LangGraph state graph."""
        try:
            from langgraph.graph import StateGraph, END
            
            # Create the graph
            builder = StateGraph(PageOCRState)
            
            # Add nodes
            builder.add_node("analyze_complexity", self._node_analyze_complexity)
            builder.add_node("ocr_tesseract", self._node_ocr_tesseract)
            builder.add_node("ocr_gemini", self._node_ocr_gemini)
            builder.add_node("post_process", self._node_post_process)
            builder.add_node("fallback", self._node_fallback)
            
            # Set entry point
            builder.set_entry_point("analyze_complexity")
            
            # Conditional routing after complexity analysis
            builder.add_conditional_edges(
                "analyze_complexity",
                self._route_engine,
                {
                    "tesseract": "ocr_tesseract",
                    "gemini": "ocr_gemini",
                }
            )
            
            # After OCR → check if fallback needed
            builder.add_conditional_edges(
                "ocr_tesseract",
                self._check_ocr_result,
                {"success": "post_process", "fallback": "fallback"}
            )
            builder.add_conditional_edges(
                "ocr_gemini",
                self._check_ocr_result,
                {"success": "post_process", "fallback": "fallback"}
            )
            
            # Fallback → route to next engine
            builder.add_conditional_edges(
                "fallback",
                self._route_fallback,
                {
                    "tesseract": "ocr_tesseract",
                    "gemini": "ocr_gemini",
                    "give_up": "post_process",
                }
            )
            
            # Post-process → END
            builder.add_edge("post_process", END)
            
            self._graph = builder.compile()
            self._compiled = True
            logger.info("✅ LangGraph OCR pipeline built successfully")
            
        except ImportError as e:
            logger.warning(f"LangGraph not available: {e}. Using fallback mode.")
            self._compiled = False
        except Exception as e:
            logger.error(f"Failed to build LangGraph pipeline: {e}")
            self._compiled = False
    
    @property
    def is_available(self) -> bool:
        return self._compiled and self._graph is not None
    
    # ─── Nodes ─────────────────────────────────────────
    
    def _get_analyzer(self):
        """Lazy-load the complexity analyzer."""
        if self._analyzer is None:
            from page_complexity_analyzer import PageComplexityAnalyzer
            self._analyzer = PageComplexityAnalyzer()
        return self._analyzer
    
    def _get_processor(self, engine: str, language: str):
        """Get or create a cached OCR processor."""
        cache_key = f"{engine}_{language}"
        if cache_key not in self._processors:
            from ocr_factory import OCRFactory
            factory = OCRFactory()
            try:
                self._processors[cache_key] = factory.create_processor(engine, language)
            except Exception as e:
                logger.warning(f"Failed to create {engine} processor: {e}")
                return None
        return self._processors[cache_key]
    
    def _node_analyze_complexity(self, state: PageOCRState) -> dict:
        """Node: Analyze page complexity and determine OCR strategy."""
        start = time.time()
        
        analyzer = self._get_analyzer()
        analysis = analyzer.analyze(state['page_image'])
        
        elapsed_ms = (time.time() - start) * 1000
        
        return {
            'complexity_score': analysis.get('complexity_score', 50),
            'has_table': analysis.get('has_table', False),
            'has_illustrations': analysis.get('has_illustrations', False),
            'has_mixed_content': analysis.get('has_mixed_content', False),
            'is_multicolumn': analysis.get('is_multicolumn', False),
            'num_columns': analysis.get('num_columns', 1),
            'text_region': analysis.get('text_region'),
            'column_gutter_x': analysis.get('column_gutter_x'),
            'image_regions': analysis.get('image_regions', []),
            'recommended_engine': analysis.get('recommended_engine', 'tesseract'),
            'reasoning': analysis.get('reasoning', ''),
            'analysis_time_ms': elapsed_ms,
            'fallback_chain': [],
            'retry_count': 0,
        }
    
    def _node_ocr_tesseract(self, state: PageOCRState) -> dict:
        """Node: Run Tesseract OCR."""
        return self._run_ocr(state, 'tesseract')
    
    def _node_ocr_gemini(self, state: PageOCRState) -> dict:
        """Node: Run Gemini Vision OCR."""
        return self._run_ocr(state, 'gemini')
    
    def _run_ocr(self, state: PageOCRState, engine: str) -> dict:
        """Execute OCR with the specified engine."""
        start = time.time()
        
        processor = self._get_processor(engine, state['language'])
        if processor is None:
            return {
                'extracted_text': '',
                'ocr_failed': True,
                'engine_used': engine,
                'ocr_time_ms': 0,
                'fallback_chain': state.get('fallback_chain', []) + [engine],
            }
        
        try:
            text = processor.extract_text(state['page_image'])
            elapsed_ms = (time.time() - start) * 1000
            
            engine_icon = {"tesseract": "🔧", "easyocr": "🚀", "gemini": "🤖"}.get(engine, "⚙️")
            logger.info(f"  {engine_icon} {engine.upper()}: {len(text)} chars in {elapsed_ms:.0f}ms")
            
            return {
                'extracted_text': text,
                'ocr_failed': len(text.strip()) == 0,
                'engine_used': engine,
                'ocr_time_ms': elapsed_ms,
                'fallback_chain': state.get('fallback_chain', []) + [engine],
            }
        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            logger.error(f"  ❌ {engine.upper()} failed: {e}")
            return {
                'extracted_text': '',
                'ocr_failed': True,
                'engine_used': engine,
                'ocr_time_ms': elapsed_ms,
                'fallback_chain': state.get('fallback_chain', []) + [engine],
            }
    
    def _node_post_process(self, state: PageOCRState) -> dict:
        """Node: Clean and post-process extracted text."""
        start = time.time()
        
        text = state.get('extracted_text', '')
        
        # Telugu post-processing
        if getattr(config, 'ENABLE_TELUGU_POST_PROCESSING', False) and text:
            try:
                from telugu_post_processor import post_process_telugu
                text = post_process_telugu(text)
            except Exception as e:
                logger.warning(f"Telugu post-processing failed: {e}")
        
        elapsed_ms = (time.time() - start) * 1000
        total_ms = (
            state.get('analysis_time_ms', 0) + 
            state.get('ocr_time_ms', 0) + 
            elapsed_ms
        )
        
        return {
            'post_processed_text': text,
            'post_process_time_ms': elapsed_ms,
            'total_time_ms': total_ms,
        }
    
    def _node_fallback(self, state: PageOCRState) -> dict:
        """Node: Prepare for fallback to next engine."""
        retry_count = state.get('retry_count', 0) + 1
        logger.info(f"  🔄 Fallback triggered (attempt {retry_count})")
        return {'retry_count': retry_count}
    
    # ─── Routing ───────────────────────────────────────
    
    def _route_engine(self, state: PageOCRState) -> str:
        """Route to the appropriate OCR engine based on complexity."""
        score = state.get('complexity_score', 50)
        recommended = state.get('recommended_engine', 'tesseract')
        
        # Check if Gemini should be used for very complex pages
        gemini_threshold = getattr(config, 'GEMINI_COMPLEXITY_THRESHOLD', 80)
        gemini_available = getattr(config, 'GEMINI_AVAILABLE', False)
        
        if score >= gemini_threshold and gemini_available:
            logger.info(f"  🤖 Routing to GEMINI (complexity: {score:.0f} >= {gemini_threshold})")
            return 'gemini'
        
        # Force engine from config override
        force_engine = getattr(config, 'OCR_ENGINE', 'hybrid').lower()
        if force_engine not in ('hybrid', 'auto'):
            return force_engine
        
        return recommended
    
    def _check_ocr_result(self, state: PageOCRState) -> str:
        """Check if OCR succeeded or needs fallback."""
        if state.get('ocr_failed', False):
            retry_count = state.get('retry_count', 0)
            if retry_count < 2:  # Max 2 fallback attempts
                return 'fallback'
        return 'success'
    
    def _route_fallback(self, state: PageOCRState) -> str:
        """Route to the next engine in the fallback chain."""
        tried = set(state.get('fallback_chain', []))
        gemini_available = getattr(config, 'GEMINI_AVAILABLE', False)
        use_gemini_fallback = getattr(config, 'GEMINI_USE_AS_FALLBACK', True)
        
        # Fallback order: tesseract → gemini
        fallback_order = ['tesseract']
        if gemini_available and use_gemini_fallback:
            fallback_order.append('gemini')
        
        for engine in fallback_order:
            if engine not in tried:
                logger.info(f"  🔄 Falling back to {engine.upper()}")
                return engine
        
        logger.warning("  ⚠️ All engines exhausted — giving up")
        return 'give_up'
    
    # ─── Public API ────────────────────────────────────
    
    def process_page(self, image: Image.Image, page_num: int, 
                     language: str = 'tel') -> PageOCRState:
        """
        Process a single page through the full LangGraph pipeline.
        
        Args:
            image: PIL Image of the page
            page_num: Page number (0-indexed)
            language: OCR language code
            
        Returns:
            Final PageOCRState with all results and timing data
        """
        if not self.is_available:
            # Fallback to simple direct processing
            return self._process_page_simple(image, page_num, language)
        
        initial_state: PageOCRState = {
            'page_image': image,
            'page_num': page_num,
            'language': language,
            'complexity_score': 0,
            'has_table': False,
            'has_illustrations': False,
            'has_mixed_content': False,
            'is_multicolumn': False,
            'num_columns': 1,
            'text_region': None,
            'column_gutter_x': None,
            'image_regions': [],
            'analysis_time_ms': 0,
            'engine_used': '',
            'recommended_engine': 'tesseract',
            'extracted_text': '',
            'ocr_time_ms': 0,
            'ocr_failed': False,
            'post_processed_text': '',
            'post_process_time_ms': 0,
            'retry_count': 0,
            'fallback_chain': [],
            'total_time_ms': 0,
            'reasoning': '',
        }
        
        try:
            result = self._graph.invoke(initial_state)
            return result
        except Exception as e:
            logger.error(f"LangGraph pipeline error: {e}, falling back to simple mode")
            return self._process_page_simple(image, page_num, language)
    
    def _process_page_simple(self, image: Image.Image, page_num: int,
                             language: str) -> PageOCRState:
        """Simple fallback when LangGraph is not available."""
        start = time.time()
        
        # Analyze
        analyzer = self._get_analyzer()
        analysis = analyzer.analyze(image)
        analysis_ms = (time.time() - start) * 1000
        
        # OCR with Tesseract
        ocr_start = time.time()
        processor = self._get_processor('tesseract', language)
        text = ''
        ocr_failed = False
        if processor:
            try:
                text = processor.extract_text(image)
            except Exception:
                ocr_failed = True
        ocr_ms = (time.time() - ocr_start) * 1000
        
        total_ms = (time.time() - start) * 1000
        
        return {
            'page_image': image,
            'page_num': page_num,
            'language': language,
            'complexity_score': analysis.get('complexity_score', 50),
            'has_table': analysis.get('has_table', False),
            'has_illustrations': analysis.get('has_illustrations', False),
            'has_mixed_content': analysis.get('has_mixed_content', False),
            'is_multicolumn': analysis.get('is_multicolumn', False),
            'num_columns': analysis.get('num_columns', 1),
            'text_region': analysis.get('text_region'),
            'column_gutter_x': analysis.get('column_gutter_x'),
            'image_regions': analysis.get('image_regions', []),
            'analysis_time_ms': analysis_ms,
            'engine_used': 'tesseract',
            'recommended_engine': analysis.get('recommended_engine', 'tesseract'),
            'extracted_text': text,
            'ocr_time_ms': ocr_ms,
            'ocr_failed': ocr_failed,
            'post_processed_text': text,
            'post_process_time_ms': 0,
            'retry_count': 0,
            'fallback_chain': ['tesseract'],
            'total_time_ms': total_ms,
            'reasoning': analysis.get('reasoning', ''),
        }
    
    def get_pipeline_diagram(self) -> str:
        """Return a text representation of the pipeline for debugging."""
        return """
        ┌─────────────────────┐
        │  analyze_complexity │
        └──────┬──┬──┬────────┘
               │  │  │
     ┌─────────┘  │  └──────────┐
     ▼            ▼             ▼
┌──────────┐ ┌──────────┐ ┌──────────┐
│ Tesseract│ │ EasyOCR  │ │  Gemini  │
└────┬─────┘ └────┬─────┘ └────┬─────┘
     │            │             │
     └─────┬──────┴─────────────┘
           │ (fallback if failed)
     ┌─────▼─────┐
     │post_process│
     └───────────┘
        """
