# GitHub Repository Setup

Follow these steps to push your YouTube Downloader project to GitHub:

1. Create a new repository on GitHub:
   - Go to https://github.com/new
   - Name the repository "youtube-downloader"
   - Add a description (optional)
   - Choose whether to make it public or private
   - Do NOT initialize with README, .gitignore, or license (we already have these)
   - Click "Create repository"

2. Connect your local repository to GitHub:
   ```bash
   git remote add origin https://github.com/yourusername/youtube-downloader.git
   ```
   (Replace "yourusername" with your actual GitHub username)

3. Push your code to GitHub:
   ```bash
   git push -u origin main
   ```

4. Verify that your code is now on GitHub by visiting:
   https://github.com/yourusername/youtube-downloader

## Updating the GitHub Button

After pushing to GitHub, you may want to update the GitHub button in the application to point to your actual repository:

1. Open `templates/layout.html`
2. Find the GitHub button link (around line 350)
3. Update the href attribute to point to your repository URL:
   ```html
   <a href="https://github.com/yourusername/youtube-downloader" class="github-button" target="_blank">
   ```
   (Replace "yourusername" with your actual GitHub username)

4. Save the file and commit the changes:
   ```bash
   git add templates/layout.html
   git commit -m "Update GitHub button URL"
   git push
   ``` 