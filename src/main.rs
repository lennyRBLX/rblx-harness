fn main() {
    match rblx_harness::run(std::env::args_os().skip(1)) {
        Ok(code) => std::process::exit(code),
        Err(error) => {
            eprintln!("harness: {error:#}");
            std::process::exit(2);
        }
    }
}
