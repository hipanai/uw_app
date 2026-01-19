#!/usr/bin/env python3
"""Quick validation tests for Feature #97."""

import sys
sys.path.insert(0, 'executions')

from upwork_anthropic_retry import (
    AnthropicRetryConfig,
    AnthropicErrorType,
    classify_anthropic_error,
    is_retryable_anthropic_error,
    retry_anthropic_call,
    AnthropicAPICallRecorder,
)

def test_all():
    print('Testing AnthropicRetryConfig...')
    config = AnthropicRetryConfig()
    assert config.max_retries == 5, 'max_retries failed'
    assert config.base_delay == 2.0, 'base_delay failed'
    assert config.get_delay(0) >= 2.0, 'get_delay(0) failed'
    assert config.get_delay(1) >= 4.0, 'get_delay(1) should be >= 4s'
    print('  PASSED')

    print('Testing error classification...')
    error = Exception('Rate limit exceeded')
    assert classify_anthropic_error(error) == AnthropicErrorType.RATE_LIMIT
    error2 = Exception('API overloaded')
    assert classify_anthropic_error(error2) == AnthropicErrorType.OVERLOADED
    print('  PASSED')

    print('Testing is_retryable...')
    assert is_retryable_anthropic_error(Exception('Rate limit'), config) == True
    assert is_retryable_anthropic_error(Exception('Timeout'), config) == True
    print('  PASSED')

    print('Testing retry_anthropic_call...')
    result = retry_anthropic_call(lambda: 'success')
    assert result == 'success'
    print('  PASSED')

    print('Testing retry with failure then success...')
    call_count = [0]
    def flaky():
        call_count[0] += 1
        if call_count[0] < 2:
            raise Exception('Rate limit')
        return 'recovered'
    test_config = AnthropicRetryConfig(max_retries=3, base_delay=0.01, jitter_factor=0)
    result = retry_anthropic_call(flaky, config=test_config)
    assert result == 'recovered'
    assert call_count[0] == 2
    print('  PASSED')

    print('Testing recorder...')
    recorder = AnthropicAPICallRecorder()
    recorder.record_retry(0, Exception('Rate limit'), 2.0)
    assert recorder.total_retries == 1
    assert recorder.had_rate_limit == True
    print('  PASSED')

    print()
    print('='*50)
    print('All Feature #97 quick tests PASSED!')
    print('='*50)
    return True

if __name__ == '__main__':
    success = test_all()
    sys.exit(0 if success else 1)
