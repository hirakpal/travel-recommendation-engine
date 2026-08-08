"""Protection against prompt injection attacks."""

import re

class InjectionProtector:
    """Detects and blocks prompt injection attempts."""
    
    # Dangerous keywords
    DANGEROUS_KEYWORDS = {
        "ignore", "forget", "override", "bypass", "disregard",
        "never mind", "actually", "wait", "hold on",
        "new instructions", "system prompt", "jailbreak",
        "admin", "root", "superuser"
    }
    
    # Patterns that indicate injection
    INJECTION_PATTERNS = [
        r"ignore.*instruction",
        r"forget.*prompt",
        r"override.*rule",
        r"new.*instruction",
        r"system.*prompt",
        r"\[.*SYSTEM.*\]",
        r"<!--.*-->",  # Comments
    ]
    
    def __init__(self):
        self.compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.INJECTION_PATTERNS]
    
    def check_input(self, user_input: str) -> tuple[bool, Optional[str]]:
        """
        Check if input contains injection attempt.
        
        Returns:
            (is_safe, reason)
        """
        
        # Check keywords
        lower_input = user_input.lower()
        for keyword in self.DANGEROUS_KEYWORDS:
            if keyword in lower_input:
                return False, f"Suspicious keyword: {keyword}"
        
        # Check patterns
        for pattern in self.compiled_patterns:
            if pattern.search(user_input):
                return False, "Potential injection pattern detected"
        
        return True, None
    
    def sanitize_output(self, response: str) -> str:
        """
        Sanitize LLM output.
        
        Removes any instruction-like content.
        """
        
        # Remove control characters
        sanitized = ''.join(char for char in response if char.isprintable() or char in '\n\t')
        
        # Remove suspicious patterns
        for pattern in self.INJECTION_PATTERNS:
            sanitized = re.sub(pattern, "[BLOCKED]", sanitized, flags=re.IGNORECASE)
        
        return sanitized
