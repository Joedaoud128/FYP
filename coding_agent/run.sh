#!/bin/bash

# ESIB AI Coding Agent - Convenience Launcher
# This wraps the main entry point for easier use

ENTRY_POINT="python3 ESIB_AiCodingAgent.py"

case "$1" in
    setup)
        echo "🔧 Running setup and validation..."
        ./setup.sh
        ;;
    
    check)
        echo "🏥 Running system health check..."
        python3 pre_check.py
        ;;
    
    generate)
        if [ -z "$2" ]; then
            echo "❌ Error: Prompt required"
            echo ""
            echo "Usage: ./run.sh generate 'your prompt here' [model]"
            echo ""
            echo "Examples:"
            echo "  ./run.sh generate 'Write a web scraper for Hacker News'"
            echo "  ./run.sh generate 'Write a CSV parser' qwen3:8b"
            exit 1
        fi
        
        echo "🤖 Starting code generation..."
        if [ -n "$3" ]; then
            # Model specified
            $ENTRY_POINT --generate "$2" --model "$3"
        else
            # Use default model
            $ENTRY_POINT --generate "$2"
        fi
        ;;
    
    debug)
        if [ -z "$2" ]; then
            echo "❌ Error: File path required"
            echo ""
            echo "Usage: ./run.sh debug path/to/script.py [model]"
            echo ""
            echo "Examples:"
            echo "  ./run.sh debug demos/03_broken_script.py"
            echo "  ./run.sh debug my_script.py qwen3:8b"
            exit 1
        fi
        
        echo "🔧 Starting debugging session..."
        if [ -n "$3" ]; then
            # Model specified
            $ENTRY_POINT --fix "$2" --model "$3"
        else
            # Use default model
            $ENTRY_POINT --fix "$2"
        fi
        ;;
    
    demo)
        echo "🎬 Running demo scenarios..."
        echo ""
        
        # Demo 1 - Simple Calculator
        echo "═══════════════════════════════════════════════════════════"
        echo "📝 Demo 1/3: Simple Calculator (qwen2.5-coder:7b)"
        echo "═══════════════════════════════════════════════════════════"
        $ENTRY_POINT --generate "$(cat demos/01_calculator.txt)"
        echo ""
        sleep 2
        
        # Demo 2 - Web Scraper
        echo "═══════════════════════════════════════════════════════════"
        echo "📝 Demo 2/3: Web Scraper (qwen3:8b)"
        echo "═══════════════════════════════════════════════════════════"
        $ENTRY_POINT --generate "$(cat demos/02_web_scraper.txt)" --model qwen3:8b
        echo ""
        sleep 2
        
        # Demo 3 - Debugging
        echo "═══════════════════════════════════════════════════════════"
        echo "📝 Demo 3/3: Debugging Example"
        echo "═══════════════════════════════════════════════════════════"
        $ENTRY_POINT --fix "demos/03_broken_script.py"
        echo ""
        
        echo "✅ Demo complete!"
        ;;
    
    help|--help|-h|"")
        echo "ESIB AI Coding Agent - Command Reference"
        echo "════════════════════════════════════════════════════════════"
        echo ""
        echo "Quick commands:"
        echo "  ./run.sh setup                          - First-time setup"
        echo "  ./run.sh check                          - Verify system health"
        echo "  ./run.sh demo                           - Run demo scenarios"
        echo "  ./run.sh generate 'prompt' [model]      - Generate code"
        echo "  ./run.sh debug path/to/file.py [model]  - Debug a script"
        echo ""
        echo "Available models:"
        echo "  qwen2.5-coder:7b (default) - Optimized for code generation"
        echo "  qwen3:8b                   - Newer general-purpose model"
        echo ""
        echo "Direct entry point (always available):"
        echo "  python ESIB_AiCodingAgent.py --generate 'prompt'"
        echo "  python ESIB_AiCodingAgent.py --generate 'prompt' --model qwen3:8b"
        echo "  python ESIB_AiCodingAgent.py --fix script.py"
        echo "  python ESIB_AiCodingAgent.py --fix script.py --model qwen3:8b"
        echo ""
        echo "Examples:"
        echo "  ./run.sh generate 'Create a CSV parser'"
        echo "  ./run.sh generate 'Build a REST API' qwen3:8b"
        echo "  ./run.sh debug generated_code/script.py"
        echo ""
        ;;
    
    *)
        echo "❌ Unknown command: $1"
        echo "Run './run.sh help' for usage information"
        exit 1
        ;;
esac
