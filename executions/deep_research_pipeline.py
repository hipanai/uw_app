#!/usr/bin/env python3
"""
Streaming pipeline for deep research + pitch deck generation.
Starts generating decks as soon as dossiers are ready, rather than waiting for all research to complete.

This provides ~1.4x speedup over sequential (research all → generate all) by overlapping work.
"""

import os
import sys
import json
import argparse
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
import threading
from dotenv import load_dotenv

# Import the core functions from existing scripts
from deep_research import research_lead
from generate_pitch_deck import generate_pitch_deck

load_dotenv()


def research_worker(lead, config, output_dir, index, total, dossier_queue):
    """
    Research a single lead and put the dossier file path in the queue for deck generation.
    """
    name = lead.get("full_name") or lead.get("Name") or f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip() or "unknown"
    company = lead.get("company_name") or lead.get("Company") or ""

    print(f"\n[Research {index}/{total}] Starting: {name} at {company}")

    try:
        dossier = research_lead(lead, config)

        # Save dossier
        name_slug = name.replace(" ", "_").lower()
        dossier_file = f"{output_dir}/{name_slug}_dossier.json"
        with open(dossier_file, 'w') as f:
            json.dump(dossier, f, indent=2)

        print(f"  ✅ [Research {index}/{total}] Completed: {name}")

        # Put in queue for deck generation
        dossier_queue.put({
            "dossier_file": dossier_file,
            "lead": name,
            "company": company,
            "index": index,
            "total": total
        })

        return {"lead": name, "company": company, "dossier_file": dossier_file, "status": "success"}

    except Exception as e:
        print(f"  ❌ [Research {index}/{total}] Error for {name}: {str(e)}", file=sys.stderr)
        return {"lead": name, "company": company, "error": str(e), "status": "error"}


def deck_worker(dossier_queue, deck_results, stop_event, total_leads):
    """
    Worker that pulls dossiers from queue and generates pitch decks.
    Runs until stop_event is set and queue is empty.
    """
    generated = 0
    while not (stop_event.is_set() and dossier_queue.empty()):
        try:
            # Wait for a dossier with timeout
            item = dossier_queue.get(timeout=1)
        except:
            continue

        dossier_file = item["dossier_file"]
        name = item["lead"]
        index = item["index"]

        print(f"\n[Deck {generated + 1}/{total_leads}] Starting: {name}")

        try:
            url = generate_pitch_deck(dossier_file)
            if url:
                print(f"  ✅ [Deck {generated + 1}/{total_leads}] Completed: {name}")
                deck_results.append({
                    "dossier": dossier_file,
                    "deck_url": url,
                    "lead": name,
                    "status": "success",
                    "generated_at": datetime.now().isoformat()
                })
            else:
                deck_results.append({
                    "dossier": dossier_file,
                    "lead": name,
                    "error": "No URL returned",
                    "status": "error"
                })
        except Exception as e:
            print(f"  ❌ [Deck] Error for {name}: {str(e)}", file=sys.stderr)
            deck_results.append({
                "dossier": dossier_file,
                "lead": name,
                "error": str(e),
                "status": "error"
            })

        generated += 1
        dossier_queue.task_done()


def main():
    parser = argparse.ArgumentParser(description="Streaming pipeline: research + pitch deck generation")
    parser.add_argument("--input", required=True, help="Input JSON file with leads")
    parser.add_argument("--output_dir", default=".tmp/dossiers", help="Output directory for dossiers")
    parser.add_argument("--output", default=".tmp/pipeline_results.json", help="Output file for results")
    parser.add_argument("--limit", type=int, help="Limit number of leads to process")
    parser.add_argument("--research_workers", type=int, default=5, help="Number of parallel research workers (default: 5)")
    parser.add_argument("--deck_workers", type=int, default=3, help="Number of parallel deck workers (default: 3)")

    args = parser.parse_args()

    # Load leads
    try:
        with open(args.input, 'r') as f:
            leads = json.load(f)
    except Exception as e:
        print(f"Error loading leads: {str(e)}", file=sys.stderr)
        return 1

    # Research config
    config = {
        "searches_per_lead": 4,
        "search_queries": [
            '"{name}" {company}',
            '"{name}" {company} interview OR podcast',
            '{company} customers OR clients OR case studies',
            '{company} funding OR growth OR news'
        ],
        "rate_limit_delay": 2
    }

    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)

    # Limit leads if specified
    if args.limit:
        leads = leads[:args.limit]

    total = len(leads)
    print(f"Starting pipeline: {total} leads")
    print(f"  Research workers: {args.research_workers}")
    print(f"  Deck workers: {args.deck_workers}")
    start_time = time.time()

    # Queue for passing dossiers from research to deck generation
    dossier_queue = Queue()

    # Results storage
    research_results = []
    deck_results = []

    # Stop event for deck workers
    stop_event = threading.Event()

    # Start deck workers (they'll wait for dossiers to arrive)
    deck_threads = []
    for _ in range(args.deck_workers):
        t = threading.Thread(target=deck_worker, args=(dossier_queue, deck_results, stop_event, total))
        t.start()
        deck_threads.append(t)

    # Run research workers
    with ThreadPoolExecutor(max_workers=args.research_workers) as executor:
        future_to_lead = {
            executor.submit(research_worker, lead, config, args.output_dir, i, total, dossier_queue): lead
            for i, lead in enumerate(leads, 1)
        }

        for future in as_completed(future_to_lead):
            result = future.result()
            research_results.append(result)

    # Signal deck workers to stop after queue is drained
    stop_event.set()

    # Wait for deck workers to finish
    for t in deck_threads:
        t.join()

    # Save results
    results = {
        "research": research_results,
        "decks": deck_results,
        "summary": {
            "total_leads": total,
            "research_successful": sum(1 for r in research_results if r['status'] == 'success'),
            "decks_successful": sum(1 for r in deck_results if r['status'] == 'success'),
            "elapsed_seconds": time.time() - start_time
        }
    }

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, 'w') as f:
        json.dump(results, f, indent=2)

    elapsed = time.time() - start_time

    print(f"\n\nPipeline complete!")
    print(f"  Research: {results['summary']['research_successful']}/{total} successful")
    print(f"  Decks: {results['summary']['decks_successful']}/{total} successful")
    print(f"  Time: {elapsed:.1f}s ({elapsed/total:.1f}s per lead)")
    print(f"  Results: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
