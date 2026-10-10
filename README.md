<h1 align="center">GitBleed</h1>

**GitBleed** is a tool designed for penetration testers and security researchers to **dump and reconstruct an entire Git repository** from a publicly exposed `.git` folder on a web server.


<br>


## Installation

You can easily install **GitBleed** directly from PyPI using `pip`. 

### Prerequisites
* Python **3.13** or higher is required.

### Standard Installation
Run the following command in your terminal:
```bash
pip install gitbleed
```

### Usage
Once installed, the `gitbleed` command will be available globally in your system or virtual environment. You can verify the installation and view available options by running:
```bash
gitbleed --help
```


<br>


## Security Warning (RCE Risk)
>[!CAUTION]
>
> Malicious Git repositories can contain **hooks** (`.git/hooks/*`) and dangerous configuration directives (such as `core.sshCommand`, `core.editor`, or `core.pager`) that may execute arbitrary commands on your system when you interact with the repository (e.g., during `git checkout`).
>
> **GitBleed** attempts to mitigate this risk by automatically sanitizing `.git/config` before running `git checkout`. However, **no mitigation is completely foolproof**. Always run this tool in **isolated environments** (containers, VMs, or sandboxes) and **never** blindly trust repositories from unknown or untrusted sources.


<br>


## Disclaimer
> [!CAUTION] 
>
> **Use this software at your own risk!**
>
> **YOU AGREE TO:**
> 1. Use only with **proper authorization**
> 2. Comply with **all applicable laws**
> 3. Assume **full liability** for misuse
> 
> **The Developer assume NO liability.**


<br>


## Credits

This project is a derivative work based on the **[git-dumper](https://github.com/arthaud/git-dumper)** utility developed by *Maxime Arthaud*. 

It specifically forks the logic established between versions **1.0.8** and **1.0.9**, building upon the community contributions from mid-2026.

The main modifications introduced in this version include:
* **Object-Oriented Refactoring:** Rewrote the core architecture to leverage Object-Oriented Programming (OOP) principles for better maintainability.
* **Visual & Display Enhancements:** Refactored terminal outputs and logging messages to provide a cleaner, more intuitive visual identification.
* **Robust Error Handling:** Integrated comprehensive exception handling to make the tool more resilient and informative during execution failures.
* **Bug Fixes:** Resolved underlying code defects and improved reliability.
* **CLI Improvements:** Added new flags for granular request control and eliminated the reliance on positional arguments for improved flexibility.


<br>


## License
This project is licensed under the Apache-2.0 License. See the [LICENSE](LICENSE) file for details.
