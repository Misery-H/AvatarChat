"""
Middleware functions for the Flask application.
Contains request/response processors and error handlers.
"""

import logging
import time
from flask import request, jsonify
from werkzeug.exceptions import RequestEntityTooLarge, BadRequest
from config.config_loader import ConfigurationError

logger = logging.getLogger(__name__)

def register_middleware(app):
    """Register all middleware with the Flask app"""
    
    # Error handling middleware
    @app.errorhandler(404)
    def not_found_error(error):
        """Handle 404 errors"""
        logger.warning(f"404 error: {request.url}")
        return jsonify({
            'error': True,
            'message': 'Resource not found',
            'code': 'NOT_FOUND'
        }), 404

    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 errors"""
        logger.error(f"500 error: {str(error)}")
        return jsonify({
            'error': True,
            'message': 'Internal server error',
            'code': 'INTERNAL_ERROR'
        }), 500

    @app.errorhandler(RequestEntityTooLarge)
    def file_too_large_error(error):
        """Handle file too large errors"""
        logger.warning(f"File too large: {request.url}")
        return jsonify({
            'error': True,
            'message': 'File size exceeds maximum limit (16MB)',
            'code': 'FILE_TOO_LARGE'
        }), 413

    @app.errorhandler(BadRequest)
    def bad_request_error(error):
        """Handle bad request errors"""
        logger.warning(f"Bad request: {request.url} - {str(error)}")
        return jsonify({
            'error': True,
            'message': 'Invalid request format',
            'code': 'BAD_REQUEST'
        }), 400

    @app.errorhandler(ConfigurationError)
    def configuration_error(error):
        """Handle configuration errors"""
        logger.error(f"Configuration error: {str(error)}")
        return jsonify({
            'error': True,
            'message': 'Configuration error - please check your setup',
            'code': 'CONFIGURATION_ERROR',
            'details': str(error)
        }), 500

    # Request/response logging
    @app.before_request
    def log_request_info():
        """Log request information and start timer"""
        request.start_time = time.time()
        logger.info(f"Request: {request.method} {request.url}")

    @app.after_request
    def log_response_info(response):
        """Log response information with timing"""
        if hasattr(request, 'start_time'):
            duration = time.time() - request.start_time
            logger.info(f"Response: {response.status_code} - Took {duration:.2f}s")
        else:
            logger.info(f"Response: {response.status_code}")
        return response