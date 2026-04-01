# Bridgeipelago - Docker

Before we start; This is fairly untested, so use at your own risk. I'm not responsible for lost data when running Bridgeipelago inside docker (or at all)



**This document assumes you know how docker works. I don't have the time or knowledge to explain this to you.**

## Step 0) Clone the repository / Download the files
Clone the repo (for that spicy up-to-date testing), or download your shosen release.

## Step 1) Bridgeipelago setup
Complete 99% of the setup tasks as specified in the main [setup.md](setup.md) documentation though step **4**.  
(Do not complete step 5 and 6)  

**IMPORTANT:** If you change the **filepaths** in the advanced-config: make sure to also change the **mounts** in `docker-compose.yaml` as well. Or the data will be lost upon the container closing. (You should know this)

## Step 2) Compose!
In the same location as the `docker-compose.yaml`, run `docker compose up -d`  
This preps the bridgeipelago docker image, and spins it up.  
It will also create a folder named "bridgeipelago" and mount the file directories to the same location for data persistence.  

Tee - Daa! :)

(if something doesn't work please open an issue in GitHub)



