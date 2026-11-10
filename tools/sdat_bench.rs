// The Tallgrass engine's side of tools/bench_sdat.py: renders sequences of an
// SDAT with the engine's synthesizer and prints the time spent rendering.
//
//     sdat_bench SDAT SECONDS RUNS NAME...
//
// The same harness as tools/sdat_bench.esk: each sequence plays looping for
// SECONDS, in blocks of 4096 frames into one reused buffer, with no file
// output. Only the render calls are timed. Each line gives the
// best of RUNS renders and a hash of the 16-bit samples, so the two programs'
// output can be compared without writing it.
use std::time::Instant;
use tallgrass_engine::sdat::{Player, Sdat};

const BLOCK: usize = 4096;

fn main() {
    let a: Vec<String> = std::env::args().collect();
    if a.len() < 5 {
        eprintln!("usage: sdat_bench SDAT SECONDS RUNS NAME...");
        std::process::exit(1);
    }
    let sdat = Sdat::parse(std::fs::read(&a[1]).expect("cannot read the SDAT")).expect("not an SDAT");
    let seconds: f64 = a[2].parse().expect("SECONDS");
    let runs: usize = a[3].parse().expect("RUNS");
    let frames = (48000.0 * seconds) as usize;
    let mut buf = vec![0f32; BLOCK * 2];
    let (mut total_frames, mut total_ns) = (0usize, 0u128);
    for name in &a[4..] {
        let mut best = u128::MAX;
        let (mut done, mut hash) = (0usize, 0u64);
        for _ in 0..runs.max(1) {
            let Some(mut p) = Player::new(&sdat, name, true) else {
                println!("{name} missing");
                break;
            };
            let (mut got_all, mut h, mut ns) = (0usize, 0xcbf29ce484222325u64, 0u128);
            while got_all < frames {
                let want = (frames - got_all).min(BLOCK);
                let t = Instant::now();
                let got = p.render(&mut buf[..want * 2]) / 2;
                ns += t.elapsed().as_nanos();
                for s in &buf[..got * 2] {
                    h = (h ^ ((s * 32767.0) as i16 as u16 as u64)).wrapping_mul(0x100000001b3);
                }
                got_all += got;
                if got < want {
                    break;
                }
            }
            best = best.min(ns);
            done = got_all;
            hash = h;
        }
        if best == u128::MAX {
            continue;
        }
        println!("{name} frames {done} ms {:.1} hash {hash:016x}", best as f64 / 1e6);
        total_frames += done;
        total_ns += best;
    }
    println!("total frames {total_frames} ms {:.1}", total_ns as f64 / 1e6);
}
