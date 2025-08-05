"""
Configuration loader for AI Avatar Chat application.
Handles loading and validation of API keys and prompts from JSON files.
"""

import json
import os
from typing import Dict, Any, Optional
from pathlib import Path


class ConfigurationError(Exception):
    """Custom exception for configuration-related errors."""
    pass


class ConfigLoader:
    """Handles loading and validation of configuration files."""
    
    def __init__(self, config_dir: str = "config"):
        """
        Initialize the configuration loader.
        
        Args:
            config_dir: Directory containing configuration files
        """
        self.config_dir = Path(config_dir)
        self._keys_config: Optional[Dict[str, Any]] = None
        self._prompts_config: Optional[Dict[str, Any]] = None
    
    def load_keys(self) -> Dict[str, Any]:
        """
        Load API keys from key.json file.
        
        Returns:
            Dictionary containing API keys and configuration
            
        Raises:
            ConfigurationError: If key.json is missing or invalid
        """
        if self._keys_config is None:
            keys_file = self.config_dir / "key.json"
            
            if not keys_file.exists():
                raise ConfigurationError(f"API keys file not found: {keys_file}")
            
            try:
                with open(keys_file, 'r', encoding='utf-8') as f:
                    keys_config = json.load(f)
                
                # Validate required keys
                self._validate_keys_config(keys_config)
                
                # Only assign after validation succeeds
                self._keys_config = keys_config
                
            except json.JSONDecodeError as e:
                raise ConfigurationError(f"Invalid JSON in keys file: {e}")
            except Exception as e:
                raise ConfigurationError(f"Error loading keys file: {e}")
        
        # At this point, self._keys_config is guaranteed to not be None
        assert self._keys_config is not None
        return self._keys_config
    
    def load_prompts(self) -> Dict[str, Any]:
        """
        Load prompts from prompt.json file.
        
        Returns:
            Dictionary containing prompts configuration
            
        Raises:
            ConfigurationError: If prompt.json is missing or invalid
        """
        if self._prompts_config is None:
            prompts_file = self.config_dir / "prompt.json"
            
            if not prompts_file.exists():
                raise ConfigurationError(f"Prompts file not found: {prompts_file}")
            
            try:
                with open(prompts_file, 'r', encoding='utf-8') as f:
                    prompts_config = json.load(f)
                
                # Validate required prompts
                self._validate_prompts_config(prompts_config)
                
                # Only assign after validation succeeds
                self._prompts_config = prompts_config
                
            except json.JSONDecodeError as e:
                raise ConfigurationError(f"Invalid JSON in prompts file: {e}")
            except Exception as e:
                raise ConfigurationError(f"Error loading prompts file: {e}")
        
        # At this point, self._prompts_config is guaranteed to not be None
        assert self._prompts_config is not None
        return self._prompts_config
    
    def _validate_keys_config(self, config: Dict[str, Any]) -> None:
        """
        Validate the structure of the keys configuration.
        
        Args:
            config: Configuration dictionary to validate
            
        Raises:
            ConfigurationError: If configuration is invalid
        """
        required_sections = ['alibaba_cloud', 'dashscope']
        
        for section in required_sections:
            if section not in config:
                raise ConfigurationError(f"Missing required section in keys config: {section}")
        
        # Validate Alibaba Cloud config
        alibaba_config = config['alibaba_cloud']
        required_alibaba_keys = ['access_key_id', 'access_key_secret', 'region']
        
        for key in required_alibaba_keys:
            if key not in alibaba_config or not alibaba_config[key]:
                raise ConfigurationError(f"Missing or empty Alibaba Cloud key: {key}")
        
        # Validate DashScope config
        dashscope_config = config['dashscope']
        if 'api_key' not in dashscope_config or not dashscope_config['api_key']:
            raise ConfigurationError("Missing or empty DashScope API key")
    
    def _validate_prompts_config(self, config: Dict[str, Any]) -> None:
        """
        Validate the structure of the prompts configuration.
        
        Args:
            config: Configuration dictionary to validate
            
        Raises:
            ConfigurationError: If configuration is invalid
        """
        required_sections = ['cartoon_generation', 'expressions', 'personality_generation', 'chat_system']
        
        for section in required_sections:
            if section not in config:
                raise ConfigurationError(f"Missing required section in prompts config: {section}")
        
        # Validate cartoon generation prompts
        if not isinstance(config['cartoon_generation'], list) or len(config['cartoon_generation']) < 4:
            raise ConfigurationError("cartoon_generation must be a list with at least 4 prompts")
        
        # Validate expressions
        expressions = config['expressions']
        required_expressions = ['happy', 'sad', 'surprised', #'angry', 'thinking', 'excited'
        ]
        
        for expression in required_expressions:
            if expression not in expressions or not expressions[expression]:
                raise ConfigurationError(f"Missing or empty expression prompt: {expression}")
        
        # Validate system prompts
        if not config['personality_generation']:
            raise ConfigurationError("personality_generation prompt cannot be empty")
        
        if not config['chat_system']:
            raise ConfigurationError("chat_system prompt cannot be empty")
    
    def get_alibaba_config(self) -> Dict[str, str]:
        """Get Alibaba Cloud configuration."""
        keys = self.load_keys()
        return keys['alibaba_cloud']
    
    def get_dashscope_key(self) -> str:
        """Get DashScope API key."""
        keys = self.load_keys()
        return keys['dashscope']['api_key']
    
    def get_appkey(self) -> Optional[str]:
        """Get application key if available."""
        keys = self.load_keys()
        return keys.get('appkey')
    
    def get_cartoon_prompts(self) -> list:
        """Get cartoon generation prompts."""
        prompts = self.load_prompts()
        return prompts['cartoon_generation']
    
    def get_expression_prompts(self) -> Dict[str, str]:
        """Get expression prompts."""
        prompts = self.load_prompts()
        return prompts['expressions']
    
    def get_personality_prompt(self) -> str:
        """Get personality generation prompt."""
        prompts = self.load_prompts()
        return prompts['personality_generation']
    
    def get_chat_system_prompt(self) -> str:
        """Get chat system prompt."""
        prompts = self.load_prompts()
        return prompts['chat_system']


# Global configuration loader instance
config_loader = ConfigLoader()