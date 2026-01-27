"""
Multimodal Processing Module for CrossTrans.
Handles image encoding and vision model capabilities.
"""
import base64
import mimetypes
import os
import fnmatch
from typing import Tuple, Optional
from src.constants import VISION_MODELS


class MultimodalProcessor:
    """Handles image processing and vision capabilities."""

    @staticmethod
    def is_vision_capable(model_name: str, provider: str) -> bool:
        """Check if a model supports vision."""
        provider = provider.lower()
        model_name = model_name.lower()
        
        if provider not in VISION_MODELS:
            return False
            
        models = VISION_MODELS[provider]
        for m in models:
            # Handle wildcards
            if '*' in m:
                if fnmatch.fnmatch(model_name, m):
                    return True
            elif m == model_name:
                return True
                
        # Heuristics for models not explicitly listed but likely vision
        if 'vision' in model_name or 'pixtral' in model_name:
            return True
            
        return False

    @staticmethod
    def encode_image_base64(image_path: str) -> Tuple[Optional[str], Optional[str]]:
        """Encode image file to base64."""
        if not os.path.exists(image_path):
            return None, None
            
        mime_type, _ = mimetypes.guess_type(image_path)
        if not mime_type:
            mime_type = 'image/jpeg'
            
        try:
            with open(image_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            return encoded_string, mime_type
        except Exception as e:
            print(f"Error encoding image: {e}")
            return None, None