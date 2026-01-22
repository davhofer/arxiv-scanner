"""Rate limiting implementation for API calls."""

import time
import threading
from collections import deque
from typing import Optional
from dataclasses import dataclass


# Import LLMProvider for type checking (avoiding circular import)
try:
    from research_digest.llm.provider import LLMProvider
except ImportError:
    # Fallback for type checking
    LLMProvider = object


@dataclass
class RateLimitError(Exception):
    """Raised when rate limit is exceeded."""
    retry_after: Optional[float] = None
    message: str = "Rate limit exceeded"


class RateLimiter:
    """Rate limiter using sliding window algorithm."""
    
    def __init__(self, max_requests_per_minute: float = 20.0):
        """Initialize rate limiter.
        
        Args:
            max_requests_per_minute: Maximum requests allowed per minute
        """
        self.max_requests_per_minute = max_requests_per_minute
        self.min_interval = 60.0 / max_requests_per_minute if max_requests_per_minute > 0 else 0
        self.requests = deque()  # Store timestamps of recent requests
        self.lock = threading.Lock()
        self.last_request_time = 0.0
    
    def acquire(self) -> float:
        """Acquire permission to make a request.
        
        Returns:
            Time to wait before making the request
            
        Raises:
            RateLimitError: If rate limit would be exceeded
        """
        with self.lock:
            current_time = time.time()
            
            # Remove old requests outside the sliding window (1 minute)
            cutoff_time = current_time - 60.0
            while self.requests and self.requests[0] < cutoff_time:
                self.requests.popleft()
            
            # Check if we would exceed the limit
            if len(self.requests) >= self.max_requests_per_minute:
                # Calculate when we can make the next request
                oldest_request = self.requests[0]
                retry_after = 60.0 - (current_time - oldest_request)
                raise RateLimitError(
                    retry_after=retry_after,
                    message=f"Rate limit exceeded. Can retry after {retry_after:.1f} seconds"
                )
            
            # Calculate minimum wait time based on min_interval
            time_since_last = current_time - self.last_request_time
            wait_time = max(0, self.min_interval - time_since_last)
            
            # Schedule the request
            self.requests.append(current_time + wait_time)
            self.last_request_time = current_time + wait_time
            
            return wait_time
    
    def record_request(self, request_time: Optional[float] = None) -> None:
        """Record that a request was made.
        
        Args:
            request_time: Time of the request (defaults to current time)
        """
        with self.lock:
            if request_time is None:
                request_time = time.time()
            
            # Remove old requests outside the sliding window
            cutoff_time = request_time - 60.0
            while self.requests and self.requests[0] < cutoff_time:
                self.requests.popleft()
            
            self.requests.append(request_time)
            self.last_request_time = request_time
    
    def get_status(self) -> dict:
        """Get current rate limiter status.
        
        Returns:
            Dictionary with current usage statistics
        """
        with self.lock:
            current_time = time.time()
            cutoff_time = current_time - 60.0
            
            # Remove old requests
            while self.requests and self.requests[0] < cutoff_time:
                self.requests.popleft()
            
            return {
                "requests_in_last_minute": len(self.requests),
                "max_requests_per_minute": self.max_requests_per_minute,
                "remaining_requests": max(0, self.max_requests_per_minute - len(self.requests)),
                "reset_time": min(self.requests) + 60.0 if self.requests else current_time,
                "min_interval": self.min_interval
            }
    
    def wait_if_needed(self) -> float:
        """Wait if rate limit would be exceeded, then record the request.
        
        Returns:
            Actual time waited
        """
        try:
            wait_time = self.acquire()
            if wait_time > 0:
                time.sleep(wait_time)
            self.record_request()
            return wait_time
        except RateLimitError as e:
            # For automatic waiting, we sleep the retry time and retry once
            if e.retry_after and e.retry_after > 0:
                time.sleep(e.retry_after + 0.1)  # Small buffer
                return self.wait_if_needed()  # Recursive retry
            raise


class RateLimitedLLMProvider:
    """Wrapper that adds rate limiting to any LLM provider."""
    
    def __init__(self, provider, rate_limiter: RateLimiter, enable_backoff: bool = True, max_backoff_time: float = 60.0):
        """Initialize rate-limited provider.
        
        Args:
            provider: The underlying LLM provider
            rate_limiter: Rate limiter instance
            enable_backoff: Enable exponential backoff for rate limit errors
            max_backoff_time: Maximum backoff time in seconds
        """
        self.provider = provider
        self.rate_limiter = rate_limiter
        self.enable_backoff = enable_backoff
        self.max_backoff_time = max_backoff_time
        self._rate_limit_errors = 0
        self._total_requests = 0
        self._consecutive_errors = 0
    
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate text with rate limiting and backoff."""
        self._total_requests += 1
        
        for attempt in range(5):  # Max 5 attempts
            try:
                # Wait if needed to respect rate limits
                wait_time = self.rate_limiter.wait_if_needed()
                
                # Make actual request
                result = self.provider.generate(prompt, system_prompt)
                
                # Reset consecutive errors on success
                self._consecutive_errors = 0
                return result
                
            except RateLimitError as e:
                self._rate_limit_errors += 1
                self._consecutive_errors += 1
                
                # For rate limit errors, use the provided retry_after or calculate backoff
                if self.enable_backoff:
                    retry_after = self._calculate_backoff_delay(e.retry_after)
                else:
                    retry_after = e.retry_after or 1.0
                
                if attempt == 4:  # Last attempt
                    raise RateLimitError(
                        retry_after=retry_after,
                        message=f"Rate limit exceeded after 5 attempts: {str(e)}"
                    ) from e
                
                # Wait and retry
                time.sleep(retry_after)
                
            except Exception as e:
                # Check if this is a rate limit error from the API
                if self._is_rate_limit_error(e):
                    self._rate_limit_errors += 1
                    self._consecutive_errors += 1
                    
                    # Calculate retry delay
                    if self.enable_backoff:
                        retry_after = self._calculate_backoff_delay(self._extract_retry_after(e))
                    else:
                        retry_after = self._extract_retry_after(e) or 2.0
                    
                    if attempt == 4:  # Last attempt
                        raise RateLimitError(
                            retry_after=retry_after,
                            message=f"API rate limit exceeded after 5 attempts: {str(e)}"
                        ) from e
                    
                    # Wait and retry
                    time.sleep(retry_after)
                else:
                    # Non-rate-limit errors are re-raised immediately
                    raise
        
        # This should never be reached, but just in case
        raise RuntimeError("Unexpected error in rate-limited LLM provider")
    
    def _calculate_backoff_delay(self, suggested_delay: Optional[float] = None) -> float:
        """Calculate exponential backoff delay."""
        # Use suggested delay if provided, otherwise use exponential backoff
        if suggested_delay:
            return min(suggested_delay, self.max_backoff_time)
        
        # Exponential backoff: 2^consecutive_errors, capped at max_backoff_time
        base_delay = 2.0 ** self._consecutive_errors
        jitter = 0.1 * base_delay  # Add 10% jitter to avoid thundering herd
        delay = base_delay + jitter
        
        return min(delay, self.max_backoff_time)
    
    def _is_rate_limit_error(self, error: Exception) -> bool:
        """Check if an exception is a rate limit error."""
        error_str = str(error).lower()
        
        # Common rate limit indicators
        rate_limit_indicators = [
            "rate limit",
            "rate_limit_exceeded",
            "too many requests",
            "quota exceeded",
            "429",
            "rate-limit-exceeded",
            "request limit",
            "maximum requests"
        ]
        
        return any(indicator in error_str for indicator in rate_limit_indicators)
    
    def _extract_retry_after(self, error: Exception) -> Optional[float]:
        """Extract retry-after time from error if available."""
        error_str = str(error).lower()
        
        # Look for retry-after in common formats
        # Example: "retry after 60 seconds", "retry-after: 60"
        import re
        
        # Try to find patterns like "retry after X seconds" or "retry-after: X"
        patterns = [
            r"retry after (\d+(?:\.\d+)?)",
            r"retry-after:\s*(\d+(?:\.\d+)?)",
            r"try again in (\d+(?:\.\d+)?)",
            r"wait (\d+(?:\.\d+)?) seconds?"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, error_str)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue
        
        return None
    
    def get_stats(self) -> dict:
        """Get rate limiting statistics."""
        rate_limiter_status = self.rate_limiter.get_status()
        return {
            **rate_limiter_status,
            "total_requests": self._total_requests,
            "rate_limit_errors": self._rate_limit_errors,
            "error_rate": self._rate_limit_errors / self._total_requests if self._total_requests > 0 else 0
        }